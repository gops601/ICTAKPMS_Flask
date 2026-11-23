from flask import request
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields

from app.extensions import db
from app.models import Batch, Student, StudentProposal, User
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import lead_domain_ids, mentor_batch_ids, student_profile
from app.services import proposal_service
from app.utils.audit import audit
from app.utils.errors import NotFound
from app.utils.files import file_download_response
from app.utils.responses import ok

bp = Blueprint("proposals", __name__, url_prefix="/api/proposals",
               description="Student-proposed problem statements and mentor approval")
SEC = [{"bearerAuth": []}]


class ProposalReviewSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    decision = fields.String(required=True)
    remarks = fields.String(load_default=None, allow_none=True)


def proposal_to_dict(p):
    s = p.student
    return {"id": p.id, "title": p.title, "summary": p.summary, "status": p.status, "remarks": p.remarks,
            "file": {"id": p.file.id, "name": p.file.original_name, "size_bytes": p.file.size_bytes},
            "student": {"id": s.id, "name": s.user.name, "registration_no": s.registration_no,
                        "batch": {"id": s.batch.id, "code": s.batch.code, "name": s.batch.name}},
            "submitted_at": p.created_at.isoformat(),
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None}


def _scoped(user):
    q = db.select(StudentProposal).join(Student, Student.id == StudentProposal.student_id)
    role = user.role_name
    if role == "admin":
        return q
    if role == "domain_lead":
        return q.join(Batch, Batch.id == Student.batch_id).where(Batch.domain_id.in_(lead_domain_ids(user) or {-1}))
    if role == "mentor":
        return q.where(Student.batch_id.in_(mentor_batch_ids(user) or {-1}))
    s = student_profile(user)
    return q.where(StudentProposal.student_id == (s.id if s else -1))


def _get(user, proposal_id):
    p = db.session.scalar(_scoped(user).where(StudentProposal.id == proposal_id))
    if not p:
        raise NotFound("Proposal not found")
    return p


@bp.get("")
@bp.doc(security=SEC)
@login_required
def list_proposals():
    a = request.args
    q = _scoped(current_user())
    if a.get("status"):
        q = q.where(StudentProposal.status == a["status"])
    if a.get("batch_id", type=int):
        q = q.where(Student.batch_id == a.get("batch_id", type=int))
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.join(User, User.id == Student.user_id).where(db.or_(StudentProposal.title.like(like), User.name.like(like)))
    q = q.order_by(StudentProposal.created_at.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int), per_page=min(a.get("per_page", 20, type=int), 100),
                       error_out=False)
    return ok([proposal_to_dict(p) for p in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.get("/mine")
@bp.doc(security=SEC, description="The student's own proposals plus whether uploading is currently allowed.")
@roles_required("student")
def my_proposals():
    student = student_profile(current_user())
    if not student:
        raise NotFound("Student profile not found")
    rows = (db.session.query(StudentProposal).filter_by(student_id=student.id)
            .order_by(StudentProposal.created_at.desc()).all())
    reason = proposal_service.upload_block_reason(student)
    return ok({"proposals": [proposal_to_dict(p) for p in rows], "can_upload": reason is None,
               "blocked_reason": reason, "has_project": proposal_service.has_project(student)})


@bp.post("")
@bp.doc(security=SEC, description="multipart/form-data: title, summary (optional), file")
@roles_required("student")
def submit_proposal():
    user = current_user()
    student = student_profile(user)
    if not student:
        raise NotFound("Student profile not found")
    p = proposal_service.submit(student, request.form.get("title"), request.form.get("summary"),
                                request.files.get("file"), user)
    audit(user.id, "proposal.submit", "student_proposal", p.id)
    db.session.commit()
    return ok(proposal_to_dict(p), "Problem statement submitted for mentor approval", 201)


@bp.post("/<int:proposal_id>/review")
@bp.doc(security=SEC, description="decision: approve | reject (remarks required when rejecting)")
@bp.arguments(ProposalReviewSchema)
@roles_required("mentor")
def review_proposal(data, proposal_id):
    user = current_user()
    p = proposal_service.review(_get(user, proposal_id), data["decision"], data["remarks"], user)
    audit(user.id, f"proposal.{p.status}", "student_proposal", p.id)
    db.session.commit()
    return ok(proposal_to_dict(p))


@bp.get("/<int:proposal_id>/download")
@bp.doc(security=SEC)
@login_required
def download_proposal(proposal_id):
    return file_download_response(_get(current_user(), proposal_id).file)
