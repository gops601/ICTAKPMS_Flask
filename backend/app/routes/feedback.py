from flask import request
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models import MentorFeedback, ProjectStudent
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_project_access, student_profile
from app.services import lifecycle
from app.services.notification_service import notify
from app.utils.audit import audit
from app.utils.errors import AppError
from app.utils.responses import ok

bp = Blueprint("feedback", __name__, url_prefix="/api/projects", description="Mentor feedback to a team or a student")
SEC = [{"bearerAuth": []}]
MAX_LEN = 5000


class FeedbackSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    message = fields.String(required=True, validate=validate.Length(min=1, max=MAX_LEN))
    student_id = fields.Integer(load_default=None, allow_none=True)  # omitted/null = the whole team


def feedback_to_dict(f):
    return {"id": f.id, "message": f.message, "created_at": f.created_at.isoformat(),
            "author": {"id": f.author_id, "name": f.author.name if f.author else "Mentor"},
            "recipient": ({"type": "student", "student_id": f.student_id, "name": f.student.user.name}
                          if f.student_id else {"type": "team", "student_id": None, "name": "Whole team"})}


@bp.get("/<int:project_id>/feedback")
@bp.doc(security=SEC, description="Students see team-wide feedback and feedback addressed to them; staff see all.")
@login_required
def list_feedback(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    q = db.select(MentorFeedback).where(MentorFeedback.project_id == project.id)
    if user.role_name == "student":
        me = student_profile(user)
        q = q.where(db.or_(MentorFeedback.student_id.is_(None), MentorFeedback.student_id == (me.id if me else -1)))
    rows = db.session.scalars(q.order_by(MentorFeedback.created_at.desc(), MentorFeedback.id.desc())).all()
    return ok([feedback_to_dict(f) for f in rows])


@bp.post("/<int:project_id>/feedback")
@bp.doc(security=SEC, description="Mentor sends feedback to the whole team or to one student of the project.")
@bp.arguments(FeedbackSchema)
@roles_required("mentor")
def send_feedback(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)  # a mentor only reaches projects they oversee
    message = data["message"].strip()
    if not message:
        raise AppError("Feedback cannot be empty", 422, {"message": "Feedback cannot be empty"})
    student_id = data["student_id"]
    if student_id is not None and not db.session.query(ProjectStudent).filter_by(
            project_id=project.id, student_id=student_id).first():
        raise AppError("That student is not a member of this project", 422, {"student_id": "Not a project member"})
    fb = MentorFeedback(project_id=project.id, student_id=student_id, author_id=user.id, message=message)
    db.session.add(fb)
    db.session.flush()
    recipients = {pm.student.user_id for pm in project.members
                  if student_id is None or pm.student_id == student_id}
    notify(recipients, "mentor_feedback", "New feedback from your mentor",
           f"{user.name}: {message[:140]}", "/student/feedback")
    lifecycle.log_activity(project.id, user.id, "feedback.sent", {"student_id": student_id})
    audit(user.id, "project.feedback", "project", project.id, {"student_id": student_id})
    db.session.commit()
    return ok(feedback_to_dict(fb), "Feedback sent", 201)
