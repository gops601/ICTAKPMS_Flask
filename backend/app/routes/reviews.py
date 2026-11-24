from datetime import date

from flask import request
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models import EvaluationTemplate, Project, ProjectReview, User
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_project_access, scoped_projects, student_profile
from app.schemas.project import project_to_dict
from app.services import evaluation_service as ev
from app.services import lifecycle
from app.services.metrics_service import project_weeks
from app.utils.audit import audit
from app.utils.errors import NotFound
from app.utils.responses import ok

bp = Blueprint("reviews", __name__, url_prefix="/api", description="Weekly evaluations, criteria templates, final sign-off")
SEC = [{"bearerAuth": []}]
MONITORS = ("mentor", "domain_lead", "admin")


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class CriterionSchema(_Base):
    id = fields.Integer(allow_none=True)
    name = fields.String(required=True)
    max_marks = fields.Raw(required=True)
    marks_obtained = fields.Raw(allow_none=True)
    remarks = fields.String(allow_none=True)


class StudentRemarkSchema(_Base):
    student_id = fields.Integer(required=True)
    remarks = fields.String(allow_none=True)
    marks_obtained = fields.Raw(allow_none=True)  # individual score (never shown to students)


class ReviewPayloadSchema(_Base):
    criteria = fields.List(fields.Nested(CriterionSchema))
    remarks = fields.String(allow_none=True)
    strengths = fields.String(allow_none=True)
    improvements = fields.String(allow_none=True)
    recommendations = fields.String(allow_none=True)
    review_date = fields.String(allow_none=True)
    student_remarks = fields.List(fields.Nested(StudentRemarkSchema))
    individual_max_marks = fields.Raw(allow_none=True)
    version = fields.Integer()


class ReviewReopenSchema(_Base):
    reason = fields.String(required=True)


class ApplyTemplateSchema(_Base):
    template_id = fields.Integer(required=True)


class SignoffSchema(_Base):
    remarks = fields.String(required=True)


class TemplateSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=1, max=120))
    week_no = fields.Integer(allow_none=True, validate=validate.Range(min=1, max=4))
    criteria = fields.List(fields.Nested(CriterionSchema), required=True, validate=validate.Length(min=1))


def _project_access(project_id):
    return ensure_project_access(current_user(), project_id)


def _review_access(review_id):
    review = ev.get_review_or_404(review_id)
    ensure_project_access(current_user(), review.project_id)     # strangers get 404
    return review


def _view(review):
    user = current_user()
    sp = student_profile(user) if user.role_name == "student" else None
    d = ev.review_to_dict(review, user.role_name, sp.id if sp else None)
    d["permissions"] = ev.review_permissions(user, review)
    if user.role_name != "student":
        from app.services.review_schedule_service import pending_request, request_to_dict
        pending = pending_request(review.id)
        d["date_request"] = request_to_dict(pending) if pending else None
        project = db.session.get(Project, review.project_id)
        # an assigned mentor can ask to move a scheduled date whenever the review is still open (not only while editing)
        d["permissions"]["can_request_date_change"] = bool(
            ev.is_assigned_mentor(user, project)
            and review.status in ev.EDITABLE and review.review_date and not pending)
        d["permissions"]["can_decide_date_request"] = bool(pending and user.role_name in ("domain_lead", "admin"))
    return d


# ------------------------------------------------------------------ project view
@bp.get("/reviews/projects/<int:project_id>")
@bp.doc(security=SEC)
@login_required
def project_reviews(project_id):
    user = current_user()
    project = _project_access(project_id)
    reviews = db.session.query(ProjectReview).filter_by(project_id=project.id).order_by(ProjectReview.week_no).all()
    signer = db.session.get(User, project.final_signed_off_by) if project.final_signed_off_by else None
    all_in = all(r.status == "submitted" for r in reviews) and len(reviews) == project_weeks(project)
    is_reviewer = user.role_name == "admin" or ev.is_assigned_mentor(user, project)
    return ok({
        "project": {"id": project.id, "title": project.title, "stage": project.stage, "stage_label": lifecycle.LABELS[project.stage]},
        "reviews": [_view(r) for r in reviews],
        "overall": ev.overall_performance(project.id, include_scores=user.role_name != "student"),
        "final_evaluation": {
            "signed_off": bool(project.final_signed_off_by), "remarks": project.final_remarks if project.final_signed_off_by else None,
            "signed_by": signer.name if signer else None,
            "can_sign_off": bool(is_reviewer and project.stage == "final_evaluation" and not project.final_signed_off_by and all_in),
            "all_reviews_submitted": all_in,
        },
    })


@bp.post("/reviews/projects/<int:project_id>/final-signoff")
@bp.doc(security=SEC, description="Mandatory final evaluation sign-off (Final Evaluation stage, all 4 reviews submitted).")
@bp.arguments(SignoffSchema)
@roles_required("mentor", "admin")
def final_signoff(data, project_id):
    user = current_user()
    project = _project_access(project_id)
    ev.final_signoff(project, data["remarks"], user)
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name), "Final evaluation signed off")


# ------------------------------------------------------------------ single review
@bp.get("/reviews/<int:review_id>")
@bp.doc(security=SEC)
@login_required
def get_review(review_id):
    return ok(_view(_review_access(review_id)))


@bp.put("/reviews/<int:review_id>")
@bp.doc(security=SEC, description="Save a draft (criteria, scores, feedback). Criteria may change until submission.")
@bp.arguments(ReviewPayloadSchema)
@roles_required("mentor")
def save_review(data, review_id):
    review = _review_access(review_id)
    ev.save_draft(review, data, current_user())
    db.session.commit()
    return ok(_view(review), "Draft saved")


@bp.post("/reviews/<int:review_id>/submit")
@bp.doc(security=SEC, description="Optionally includes the same payload as PUT, applied atomically before submitting.")
@bp.arguments(ReviewPayloadSchema)
@roles_required("mentor")
def submit_review(data, review_id):
    review = _review_access(review_id)
    ev.submit(review, data, current_user())
    db.session.commit()
    return ok(_view(review), "Evaluation submitted")


@bp.post("/reviews/<int:review_id>/reopen")
@bp.doc(security=SEC, description="Send a submitted evaluation back for updating (mentor, Domain Lead or admin). Reason required, "
                                  "previous state snapshotted. Only mentors can score.")
@bp.arguments(ReviewReopenSchema)
@roles_required("mentor", "domain_lead", "admin")
def reopen_review(data, review_id):
    review = _review_access(review_id)
    ev.reopen(review, data["reason"], current_user())
    db.session.commit()
    return ok(_view(review), "Evaluation reopened")


@bp.get("/reviews/<int:review_id>/revisions")
@bp.doc(security=SEC)
@roles_required(*MONITORS)
def get_revisions(review_id):
    return ok(ev.revisions(_review_access(review_id)))


@bp.post("/reviews/<int:review_id>/apply-template")
@bp.doc(security=SEC)
@bp.arguments(ApplyTemplateSchema)
@roles_required("mentor")
def apply_template(data, review_id):
    user = current_user()
    review = _review_access(review_id)
    t = db.session.get(EvaluationTemplate, data["template_id"])
    if not t or t.owner_id != user.id:
        raise NotFound("Template not found")
    ev.apply_template(review, t, user)
    db.session.commit()
    return ok(_view(review), "Template applied")


# ------------------------------------------------------------------------ queue
@bp.get("/reviews/queue")
@bp.doc(security=SEC, description="Reviews still to be completed, scoped by role (mentor / lead / admin).")
@roles_required(*MONITORS)
def queue():
    a = request.args
    visible = scoped_projects(current_user()).subquery()
    stage_ok = db.or_(
        db.and_(ProjectReview.week_no == 1, Project.stage.notin_(["allocated", "completed"])),
        db.and_(ProjectReview.week_no > 1, Project.stage.in_(["implementation", "final_evaluation"])))
    q = (db.select(ProjectReview).join(Project, Project.id == ProjectReview.project_id)
         .join(visible, visible.c.id == Project.id)
         .where(ProjectReview.status != "submitted", stage_ok))
    if a.get("batch_id", type=int):
        q = q.where(Project.batch_id == a.get("batch_id", type=int))
    if a.get("week", type=int):
        q = q.where(ProjectReview.week_no == a.get("week", type=int))
    if a.get("status") in ("pending", "draft", "reopened"):
        q = q.where(ProjectReview.status == a["status"])
    if a.get("overdue") in ("1", "true"):
        q = q.where(ProjectReview.due_date < date.today())
    q = q.order_by(ProjectReview.due_date.asc(), ProjectReview.id)
    page = db.paginate(q, page=a.get("page", 1, type=int), per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    items = []
    for r in page.items:
        p = db.session.get(Project, r.project_id)
        items.append({"review_id": r.id, "week_no": r.week_no, "status": r.status, "status_label": ev.STATUS_LABEL[r.status],
                      "due_date": r.due_date.isoformat() if r.due_date else None,
                      "is_overdue": bool(r.due_date and r.due_date < date.today()),
                      "project": {"id": p.id, "title": p.title, "batch": p.batch.code,
                                  "students": [m.student.user.name for m in p.members]}})
    return ok(items, meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


# -------------------------------------------------------------- criteria templates
def _tpl(t):
    return {"id": t.id, "name": t.name, "week_no": t.week_no, "criteria": t.criteria,
            "total_marks": sum(c["max_marks"] for c in t.criteria)}


def _own_template(template_id):
    t = db.session.get(EvaluationTemplate, template_id)
    if not t or t.owner_id != current_user().id:
        raise NotFound("Template not found")
    return t


@bp.get("/evaluation-criteria/templates")
@bp.doc(security=SEC)
@roles_required("mentor")
def list_templates():
    q = db.select(EvaluationTemplate).where(EvaluationTemplate.owner_id == current_user().id)
    if request.args.get("week", type=int):
        q = q.where(db.or_(EvaluationTemplate.week_no == request.args.get("week", type=int), EvaluationTemplate.week_no.is_(None)))
    return ok([_tpl(t) for t in db.session.scalars(q.order_by(EvaluationTemplate.week_no, EvaluationTemplate.name))])


@bp.post("/evaluation-criteria/templates")
@bp.doc(security=SEC)
@bp.arguments(TemplateSchema)
@roles_required("mentor")
def create_template(data):
    user = current_user()
    t = EvaluationTemplate(owner_id=user.id, name=data["name"].strip(), week_no=data.get("week_no"),
                           criteria=ev.clean_template_criteria(data["criteria"]))
    db.session.add(t)
    db.session.commit()
    return ok(_tpl(t), "Template created", 201)


@bp.put("/evaluation-criteria/templates/<int:template_id>")
@bp.doc(security=SEC)
@bp.arguments(TemplateSchema)
@roles_required("mentor")
def update_template(data, template_id):
    t = _own_template(template_id)
    t.name, t.week_no = data["name"].strip(), data.get("week_no")
    t.criteria = ev.clean_template_criteria(data["criteria"])
    db.session.commit()
    return ok(_tpl(t))


@bp.delete("/evaluation-criteria/templates/<int:template_id>")
@bp.doc(security=SEC)
@roles_required("mentor")
def delete_template(template_id):
    db.session.delete(_own_template(template_id))
    db.session.commit()
    return ok(message="Template deleted")


@bp.post("/evaluation-criteria/templates/samples")
@bp.doc(security=SEC, description="Creates editable example templates (weeks 1–4) for the caller. Idempotent.")
@roles_required("mentor")
def sample_templates():
    created = ev.create_samples(current_user())
    db.session.commit()
    return ok([_tpl(t) for t in created], f"{len(created)} sample template(s) added", 201)
