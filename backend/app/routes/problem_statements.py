import io

from flask import request, send_file
from flask_smorest import Blueprint

from app.extensions import db
from app.models import ProblemStatement, ProblemStatementDataset, ProblemStatementDocument
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import can_access_domain, can_view_problem_statement, lead_domain_ids
from app.schemas.problem import (ProblemStatementSchema, ProblemStatementUpdateSchema, PSStatusSchema,
                                 file_to_dict, ps_to_dict)
from app.services import file_service, problem_service
from app.services.templates import build_template
from app.utils.audit import audit
from app.utils.errors import AppError, NotFound
from app.utils.files import file_download_response
from app.utils.responses import ok

bp = Blueprint("problem_statements", __name__, url_prefix="/api/problem-statements",
               description="Problem statements, datasets and reference documents")
SEC = [{"bearerAuth": []}]
MANAGERS = ("admin", "domain_lead")


def _viewable(ps_id):
    """Fetch a statement the current user may view; hide existence otherwise."""
    ps = db.session.get(ProblemStatement, ps_id)
    if not ps or not can_view_problem_statement(current_user(), ps):
        raise NotFound("Problem statement not found")
    return ps


def _editable(ps_id):
    ps = db.session.get(ProblemStatement, ps_id)
    if not ps or not can_access_domain(current_user(), ps.domain_id):
        raise NotFound("Problem statement not found")
    return ps


@bp.get("")
@bp.doc(security=SEC)
@roles_required(*MANAGERS)
def list_problem_statements():
    user, a = current_user(), request.args
    q = db.select(ProblemStatement)
    if user.role_name == "domain_lead":
        q = q.where(ProblemStatement.domain_id.in_(lead_domain_ids(user) or {-1}))
    if a.get("domain_id", type=int):
        q = q.where(ProblemStatement.domain_id == a.get("domain_id", type=int))
    if a.get("difficulty") in problem_service.DIFFICULTIES:
        q = q.where(ProblemStatement.difficulty == a["difficulty"])
    if a.get("status") in problem_service.STATUSES:
        q = q.where(ProblemStatement.status == a["status"])
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.where(db.or_(ProblemStatement.title.like(like), ProblemStatement.ps_code.like(like)))
    sort = {"title": ProblemStatement.title, "ps_code": ProblemStatement.ps_code,
            "difficulty": ProblemStatement.difficulty}.get(a.get("sort"), ProblemStatement.created_at)
    q = q.order_by(sort.asc() if a.get("order") == "asc" else sort.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    return ok([ps_to_dict(p) for p in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.post("")
@bp.doc(security=SEC)
@bp.arguments(ProblemStatementSchema)
@roles_required(*MANAGERS)
def create_problem_statement(data):
    user = current_user()
    clean, errors = problem_service.validate_ps_data(data, user)
    if errors:
        raise AppError("Validation failed", 422, errors)
    ps = problem_service.create_ps(clean, user)
    audit(user.id, "problem_statement.create", "problem_statement", ps.id, {"code": ps.ps_code})
    db.session.commit()
    return ok(ps_to_dict(ps, True, True), "Problem statement created", 201)


@bp.get("/template")
@bp.doc(security=SEC)
@roles_required(*MANAGERS)
def template():
    fmt = request.args.get("format", "xlsx")
    if fmt not in ("csv", "xlsx"):
        raise AppError("format must be csv or xlsx", 422)
    content, mime = build_template("problem_statements", None, fmt)
    return send_file(io.BytesIO(content), mimetype=mime, as_attachment=True,
                     download_name=f"problem_statements_template.{fmt}")


@bp.get("/<int:ps_id>")
@bp.doc(security=SEC)
@login_required
def get_problem_statement(ps_id):
    ps = _viewable(ps_id)
    return ok(ps_to_dict(ps, True, can_access_domain(current_user(), ps.domain_id)))


@bp.put("/<int:ps_id>")
@bp.doc(security=SEC)
@bp.arguments(ProblemStatementUpdateSchema)
@roles_required(*MANAGERS)
def update_problem_statement(data, ps_id):
    ps = problem_service.update_ps(_editable(ps_id), data, current_user())
    audit(current_user().id, "problem_statement.update", "problem_statement", ps.id)
    db.session.commit()
    return ok(ps_to_dict(ps, True, True))


@bp.patch("/<int:ps_id>/status")
@bp.doc(security=SEC)
@bp.arguments(PSStatusSchema)
@roles_required(*MANAGERS)
def set_status(data, ps_id):
    ps = problem_service.set_status(_editable(ps_id), data["status"])
    audit(current_user().id, f"problem_statement.{ps.status}", "problem_statement", ps.id)
    db.session.commit()
    return ok(ps_to_dict(ps, True, True))


# ------------------------------------------------------------------ attachments
KINDS = {
    "datasets": ("dataset", ProblemStatementDataset, "datasets"),
    "documents": ("reference_document", ProblemStatementDocument, "documents"),
}


def _kind(kind):
    if kind not in KINDS:
        raise NotFound("Unknown attachment type")
    return KINDS[kind]


@bp.post("/<int:ps_id>/<kind>")
@bp.doc(security=SEC, description="multipart/form-data: file, description (optional). kind = datasets | documents")
@roles_required(*MANAGERS)
def upload_attachment(ps_id, kind):
    category, model, rel = _kind(kind)
    ps = _editable(ps_id)
    attachment = file_service.save_upload(request.files.get("file"), category, current_user().id)
    link = model(problem_statement_id=ps.id, file_id=attachment.id,
                 description=(request.form.get("description") or "").strip()[:255] or None)
    db.session.add(link)
    audit(current_user().id, f"problem_statement.{category}_upload", "problem_statement", ps.id,
          {"file": attachment.original_name})
    db.session.commit()
    return ok(file_to_dict(link), "File uploaded", 201)


def _link(ps_id, kind, link_id, editable):
    _, model, _ = _kind(kind)
    ps = _editable(ps_id) if editable else _viewable(ps_id)
    link = db.session.get(model, link_id)
    if not link or link.problem_statement_id != ps.id:
        raise NotFound("File not found")
    return ps, link


@bp.get("/<int:ps_id>/<kind>/<int:link_id>/download")
@bp.doc(security=SEC)
@login_required
def download_attachment(ps_id, kind, link_id):
    _, link = _link(ps_id, kind, link_id, editable=False)
    return file_download_response(link.file)


@bp.delete("/<int:ps_id>/<kind>/<int:link_id>")
@bp.doc(security=SEC)
@roles_required(*MANAGERS)
def delete_attachment(ps_id, kind, link_id):
    ps, link = _link(ps_id, kind, link_id, editable=True)
    attachment = link.file
    db.session.delete(link)
    db.session.flush()
    file_service.delete_file(attachment)
    audit(current_user().id, "problem_statement.file_delete", "problem_statement", ps.id,
          {"file": attachment.original_name})
    db.session.commit()
    return ok(message="File removed")
