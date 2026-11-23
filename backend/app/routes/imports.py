from flask import Response, request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import ImportJob
from app.permissions import current_user, roles_required
from app.services import import_service, org_service
from app.utils.errors import AppError, Forbidden, NotFound
from app.utils.responses import ok

bp = Blueprint("imports", __name__, url_prefix="/api/imports", description="Bulk imports")
SEC = [{"bearerAuth": []}]
# Which roles may run each import type.
TYPE_ROLES = {"batches": {"admin"}, "students": {"admin"}, "problem_statements": {"admin", "domain_lead"}}
ANY_IMPORT_ROLE = ("admin", "domain_lead")


def _check_role(import_type):
    if current_user().role_name not in TYPE_ROLES.get(import_type, set()):
        raise Forbidden()


def _job_dict(job, extra=None):
    d = {"id": job.id, "import_type": job.import_type, "ou_id": job.ou_id, "filename": job.filename,
         "status": job.status, "total_rows": job.total_rows, "valid_rows": job.valid_rows,
         "error_rows": job.error_rows, "imported_rows": job.imported_rows,
         "created_at": job.created_at.isoformat()}
    d.update(extra or {})
    return d


def _own_job(job_id):
    job = db.session.get(ImportJob, job_id)
    if not job or job.user_id != current_user().id:
        raise NotFound("Import job not found")
    _check_role(job.import_type)
    return job


@bp.post("/<import_type>")
@bp.doc(security=SEC, description="multipart/form-data with fields: file, ou_id")
@roles_required(*ANY_IMPORT_ROLE)
def upload(import_type):
    import_service.get_importer(import_type)
    _check_role(import_type)
    ou = None
    if import_type in ("batches", "students"):
        ou_id = request.form.get("ou_id", type=int)
        if not ou_id:
            raise AppError("ou_id is required", 422)
        ou = org_service.get_ou(ou_id)
    f = request.files.get("file")
    if not f or not f.filename:
        raise AppError("A file is required", 422)
    job, preview, ignored = import_service.preview(import_type, ou, f.filename, f.read(), current_user())
    return ok(_job_dict(job, {"preview": preview, "ignored_columns": ignored}), "File validated", 201)


@bp.get("/<int:job_id>")
@bp.doc(security=SEC)
@roles_required(*ANY_IMPORT_ROLE)
def get_job(job_id):
    job = _own_job(job_id)
    errors = [{"row_number": e.row_number, "field": e.field, "message": e.message}
              for e in sorted(job.errors, key=lambda e: e.row_number)]
    return ok(_job_dict(job, {"errors": errors}))


@bp.post("/<int:job_id>/confirm")
@bp.doc(security=SEC)
@roles_required(*ANY_IMPORT_ROLE)
def confirm(job_id):
    body = request.get_json(silent=True) or {}
    job, extra = import_service.confirm(_own_job(job_id), current_user(), bool(body.get("import_valid_only")))
    return ok(_job_dict(job, {"credentials": extra} if extra else {}), f"{job.imported_rows} record(s) imported")


@bp.get("/<int:job_id>/errors.csv")
@bp.doc(security=SEC)
@roles_required(*ANY_IMPORT_ROLE)
def errors_csv(job_id):
    job = _own_job(job_id)
    return Response(import_service.errors_csv(job), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=import_{job.id}_errors.csv"})
