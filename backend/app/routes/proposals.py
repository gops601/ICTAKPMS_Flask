from flask import request
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields

from app.extensions import db
from app.models import Batch, Student, StudentProposal, User
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import lead_domain_ids, mentor_batch_ids, student_profile
from app.services import data_collection, proposal_service
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
            "data_collection": p.data_collection or [],
            "datasets": [{"id": d.id, "name": d.file.original_name, "size_bytes": d.file.size_bytes} for d in p.datasets],
            "subdomain": {"id": p.subdomain.id, "name": p.subdomain.name} if p.subdomain else None,
            "shelf": {"id": p.problem_statement.id, "ps_code": p.problem_statement.ps_code} if p.problem_statement else None,
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


@bp.get("/project-template")
@bp.doc(security=SEC, description="The same project template used on the Project Shelf (format=xlsx|csv), as a sample for students.")
@login_required
def project_template():
    import io
    from flask import send_file
    from app.services.templates import build_template
    from app.utils.errors import AppError
    fmt = request.args.get("format", "xlsx")
    if fmt not in ("csv", "xlsx"):
        raise AppError("format must be csv or xlsx", 422)
    content, mime = build_template("problem_statements", None, fmt)
    return send_file(io.BytesIO(content), mimetype=mime, as_attachment=True, download_name=f"project_template.{fmt}")


@bp.get("/data-template")
@bp.doc(security=SEC, description="Excel template for the detailed data-collection sheet (one row per dataset), with an example and instructions.")
@login_required
def data_template():
    from flask import Response
    return Response(data_collection.build_template(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="data-collection-template.xlsx"'})


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
    domain = student.batch.domain
    return ok({"proposals": [proposal_to_dict(p) for p in rows], "can_upload": reason is None,
               "domain": {"id": domain.id, "name": domain.name} if domain else None,
               "subdomains": [{"id": s.id, "name": s.name} for s in (domain.subdomains if domain else []) if s.is_active],
               "blocked_reason": reason, "has_project": proposal_service.has_project(student)})


@bp.post("")
@bp.doc(security=SEC, description="multipart/form-data: title, summary, subdomain_id (when the domain has subdomains), file (detailed "
                                  "document) and any number (up to 10) of `datasets` files. When datasets are attached, `data_sheet` (the filled Excel data-collection template) is required. Approval puts it on the Project Shelf.")
@roles_required("student")
def submit_proposal():
    user = current_user()
    student = student_profile(user)
    if not student:
        raise NotFound("Student profile not found")
    p = proposal_service.submit(student, request.form.get("title"), request.form.get("summary"),
                                request.files.get("file"), user, request.files.getlist("datasets"),
                                request.form.get("subdomain_id", type=int), request.files.get("data_sheet"))
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


@bp.get("/<int:proposal_id>/datasets/<int:dataset_id>/download")
@bp.doc(security=SEC)
@login_required
def download_proposal_dataset(proposal_id, dataset_id):
    p = _get(current_user(), proposal_id)
    ds = next((d for d in p.datasets if d.id == dataset_id), None)
    if not ds:
        raise NotFound("Dataset not found")
    return file_download_response(ds.file)


@bp.get("/<int:proposal_id>/download")
@bp.doc(security=SEC)
@login_required
def download_proposal(proposal_id):
    return file_download_response(_get(current_user(), proposal_id).file)
