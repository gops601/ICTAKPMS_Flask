from flask import request
from sqlalchemy.exc import IntegrityError
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Batch, BatchMentor, Mentor, Student
from app.permissions import current_user, roles_required
from app.permissions.scope import ensure_batch_access, scoped_batches
from app.schemas.org import BatchSchema, BatchUpdateSchema, ProjectDatesSchema, StatusSchema, batch_to_dict, mentor_to_dict
from app.schemas.project import BatchMentorSchema, ReassignMentorSchema
from app.services import org_service, project_service
from app.utils.audit import audit
from app.utils.errors import AppError, NotFound
from app.utils.responses import ok

bp = Blueprint("batches", __name__, url_prefix="/api/batches", description="Batches")
SEC = [{"bearerAuth": []}]
ALL = ("admin", "domain_lead", "mentor", "student")


def _notify_leads(batch):
    from app.services.notification_service import domain_lead_user_ids, notify
    notify(domain_lead_user_ids(batch.domain_id), "batch_assigned", "Batch assigned to your domain",
           f"Batch {batch.code} – {batch.name} was assigned to {batch.domain.name}. "
           "Please set the project start and end dates for this batch.", f"/lead/batches/{batch.id}")


def _student_counts(ids):
    if not ids:
        return {}
    return dict(db.session.query(Student.batch_id, db.func.count(Student.id))
                .filter(Student.batch_id.in_(ids)).group_by(Student.batch_id).all())


@bp.get("")
@bp.doc(security=SEC)
@roles_required(*ALL)
def list_batches():
    q = scoped_batches(current_user())
    a = request.args
    if a.get("ou_id", type=int):
        q = q.where(Batch.ou_id == a.get("ou_id", type=int))
    if a.get("domain_id", type=int):
        q = q.where(Batch.domain_id == a.get("domain_id", type=int))
    if a.get("status") in ("active", "closed"):
        q = q.where(Batch.status == a["status"])
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.where(db.or_(Batch.name.like(like), Batch.code.like(like)))
    sort = {"name": Batch.name, "code": Batch.code, "start_date": Batch.start_date}.get(a.get("sort"), Batch.created_at)
    q = q.order_by(sort.asc() if a.get("order") == "asc" else sort.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    counts = _student_counts([b.id for b in page.items])
    return ok([batch_to_dict(b, counts.get(b.id, 0), details=False) for b in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.post("")
@bp.doc(security=SEC)
@bp.arguments(BatchSchema)
@roles_required("admin")
def create_batch(data):
    batch = org_service.create_batch(data)
    audit(current_user().id, "batch.create", "batch", batch.id, {"code": batch.code})
    _notify_leads(batch)
    db.session.commit()
    return ok(batch_to_dict(batch, 0), "Batch created", 201)


@bp.get("/<int:batch_id>")
@bp.doc(security=SEC)
@roles_required(*ALL)
def get_batch(batch_id):
    batch = ensure_batch_access(current_user(), batch_id)
    return ok(batch_to_dict(batch, org_service.batch_student_count(batch.id)))


@bp.put("/<int:batch_id>")
@bp.doc(security=SEC)
@bp.arguments(BatchUpdateSchema)
@roles_required("admin")
def update_batch(data, batch_id):
    existing = org_service.get_batch_or_404(batch_id)
    old_domain = existing.domain_id
    batch = org_service.update_batch(existing, data)
    audit(current_user().id, "batch.update", "batch", batch.id)
    if batch.domain_id != old_domain:
        _notify_leads(batch)
    db.session.commit()
    return ok(batch_to_dict(batch, org_service.batch_student_count(batch.id)))


@bp.put("/<int:batch_id>/project-dates")
@bp.doc(security=SEC, description="Domain lead (or admin) sets when projects in this batch start and end.")
@bp.arguments(ProjectDatesSchema)
@roles_required("admin", "domain_lead")
def set_project_dates(data, batch_id):
    user = current_user()
    batch = org_service.set_project_dates(ensure_batch_access(user, batch_id), data["project_start_date"],
                                          data["project_end_date"])
    audit(user.id, "batch.project_dates", "batch", batch.id, data)
    db.session.commit()
    return ok(batch_to_dict(batch, org_service.batch_student_count(batch.id)), "Project dates saved")


@bp.delete("/<int:batch_id>")
@bp.doc(security=SEC, description="Admin only. Refused (409) while the batch has projects; students must be deleted first "
                                  "or with ?with_students=1 (which also deletes their accounts).")
@roles_required("admin")
def delete_batch(batch_id):
    user = current_user()
    batch = org_service.get_batch_or_404(batch_id)
    try:
        info = org_service.delete_batch(batch, user, with_students=request.args.get("with_students") in ("1", "true"))
        audit(user.id, "batch.delete", "batch", batch_id, info)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AppError("This batch is still referenced by other records. Close it instead.", 409)
    return ok(message=f"Batch {info['code']} was deleted")


@bp.patch("/<int:batch_id>/status")
@bp.doc(security=SEC)
@bp.arguments(StatusSchema)
@roles_required("admin")
def set_status(data, batch_id):
    batch = org_service.set_batch_status(org_service.get_batch_or_404(batch_id), data["status"])
    audit(current_user().id, f"batch.{batch.status}", "batch", batch.id)
    db.session.commit()
    return ok(batch_to_dict(batch, org_service.batch_student_count(batch.id)))


# ------------------------------------------------------------ batch mentors
MANAGERS = ("admin", "domain_lead")


def _mentor_or_404(mentor_id):
    m = db.session.get(Mentor, mentor_id)
    if not m:
        raise NotFound("Mentor not found")
    return m


def _batch_mentors(batch):
    links = db.session.query(BatchMentor).filter_by(batch_id=batch.id, is_active=True).all()
    return [mentor_to_dict(l.mentor) for l in links]


@bp.get("/<int:batch_id>/mentors")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead", "mentor")
def list_batch_mentors(batch_id):
    return ok(_batch_mentors(ensure_batch_access(current_user(), batch_id)))


@bp.post("/<int:batch_id>/mentors")
@bp.doc(security=SEC)
@bp.arguments(BatchMentorSchema)
@roles_required(*MANAGERS)
def assign_mentor(data, batch_id):
    user = current_user()
    batch = ensure_batch_access(user, batch_id)
    project_service.assign_batch_mentor(batch, _mentor_or_404(data["mentor_id"]), user)
    audit(user.id, "batch.mentor_assign", "batch", batch.id, data)
    db.session.commit()
    return ok(_batch_mentors(batch), "Mentor assigned", 201)


@bp.delete("/<int:batch_id>/mentors/<int:mentor_id>")
@bp.doc(security=SEC)
@roles_required(*MANAGERS)
def remove_mentor(batch_id, mentor_id):
    user = current_user()
    batch = ensure_batch_access(user, batch_id)
    project_service.remove_batch_mentor(batch, _mentor_or_404(mentor_id))
    audit(user.id, "batch.mentor_remove", "batch", batch.id, {"mentor_id": mentor_id})
    db.session.commit()
    return ok(_batch_mentors(batch), "Mentor removed")


@bp.post("/<int:batch_id>/mentors/<int:mentor_id>/reassign")
@bp.doc(security=SEC)
@bp.arguments(ReassignMentorSchema)
@roles_required(*MANAGERS)
def reassign_mentor(data, batch_id, mentor_id):
    user = current_user()
    batch = ensure_batch_access(user, batch_id)
    project_service.reassign_batch_mentor(batch, _mentor_or_404(mentor_id), _mentor_or_404(data["to_mentor_id"]), user)
    audit(user.id, "batch.mentor_reassign", "batch", batch.id, {"from": mentor_id, "to": data["to_mentor_id"]})
    db.session.commit()
    return ok(_batch_mentors(batch), "Mentor reassigned")
