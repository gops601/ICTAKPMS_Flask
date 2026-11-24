from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.services.domain_sync_service import mentor_in_domains
from app.models import BatchMentor, Mentor, Project, ProjectMentor, ProjectStudent, Student, User
from app.permissions import current_user, roles_required
from app.permissions.scope import lead_domain_ids, scoped_batches
from app.schemas.org import CredentialsSchema, StudentCreateSchema, mentor_to_dict, student_to_dict
from app.services import user_service
from app.utils.audit import audit
from app.utils.responses import ok

bp = Blueprint("students", __name__, url_prefix="/api", description="Students and mentors")
SEC = [{"bearerAuth": []}]


def _meta(page):
    return {"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages}


def _project_summaries(student_ids):
    """Current project (if any) per student, so allocation screens can show who is already placed."""
    if not student_ids:
        return {}
    rows = (db.session.query(ProjectStudent.student_id, Project.id, Project.stage, Project.title)
            .join(Project, Project.id == ProjectStudent.project_id)
            .filter(ProjectStudent.student_id.in_(student_ids)).all())
    return {sid: {"id": pid, "stage": stage, "title": title} for sid, pid, stage, title in rows}


@bp.get("/students")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead", "mentor")
def list_students():
    a = request.args
    visible = scoped_batches(current_user()).subquery()
    q = db.select(Student).join(visible, visible.c.id == Student.batch_id).join(User, User.id == Student.user_id)
    if a.get("batch_id", type=int):
        q = q.where(Student.batch_id == a.get("batch_id", type=int))
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.where(db.or_(User.name.like(like), User.email.like(like), Student.registration_no.like(like)))
    sort = {"name": User.name, "registration_no": Student.registration_no}.get(a.get("sort"), Student.created_at)
    q = q.order_by(sort.asc() if a.get("order", "asc") == "asc" else sort.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    projects = _project_summaries([s.id for s in page.items])
    return ok([{**student_to_dict(s), "project": projects.get(s.id)} for s in page.items], meta=_meta(page))


@bp.post("/students")
@bp.doc(security=SEC)
@bp.arguments(StudentCreateSchema)
@roles_required("admin")
def create_student(data):
    batch = user_service.ensure_batch(data["batch_id"])
    student, temp = user_service.create_student(batch, data["name"], data["email"], data["phone"],
                                                data["registration_no"], data["extra_fields"])
    audit(current_user().id, "student.create", "student", student.id, {"batch": batch.code})
    db.session.commit()
    return ok({**student_to_dict(student), "temporary_password": temp}, "Student created", 201)


@bp.post("/students/credentials")
@bp.doc(security=SEC, description="Issue fresh temporary passwords for a batch's students who have not logged in yet, "
                                  "for sharing. Passwords are returned once and never stored in clear text.")
@bp.arguments(CredentialsSchema)
@roles_required("admin")
def issue_credentials(data):
    batch = user_service.ensure_batch(data["batch_id"])
    issued, skipped = user_service.issue_batch_credentials(batch, data["student_ids"])
    audit(current_user().id, "student.credentials_issued", "batch", batch.id, {"issued": len(issued), "skipped": len(skipped)})
    db.session.commit()
    return ok({"credentials": issued, "skipped": skipped, "batch": {"code": batch.code, "name": batch.name}},
              f"{len(issued)} credential(s) issued")


@bp.get("/mentors")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def list_mentors():
    a = request.args
    user = current_user()
    q = db.select(Mentor).join(User, User.id == Mentor.user_id)
    if user.role_name == "domain_lead":
        # A lead sees mentors of their own domain(s) plus mentors not yet tied to any domain.
        q = q.where(db.or_(mentor_in_domains(lead_domain_ids(user)), Mentor.domain_id.is_(None)))
    if a.get("domain_id", type=int):
        q = q.where(mentor_in_domains([a.get("domain_id", type=int)]))
    if a.get("for_domain", type=int):  # eligible for a batch of this domain: its own mentors (leads included) + mentors not tied to a domain
        q = q.where(db.or_(mentor_in_domains([a.get("for_domain", type=int)]), Mentor.domain_id.is_(None)))
    if a.get("mentor_type") in ("internal", "industry"):
        q = q.where(Mentor.mentor_type == a["mentor_type"])
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.where(db.or_(User.name.like(like), User.email.like(like), Mentor.company.like(like)))
    q = q.order_by(User.name)
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    ids = [m.id for m in page.items]
    batches = dict(db.session.query(BatchMentor.mentor_id, db.func.count(BatchMentor.id))
                   .filter(BatchMentor.mentor_id.in_(ids), BatchMentor.is_active.is_(True))
                   .group_by(BatchMentor.mentor_id).all()) if ids else {}
    return ok([{**mentor_to_dict(m), "batch_count": batches.get(m.id, 0), "project_count": _workload(m.id)}
               for m in page.items], meta=_meta(page))


def _workload(mentor_id):
    """Projects overseen via a per-project override, or via an active batch assignment without an override."""
    via_override = db.session.query(Project.id).filter(db.or_(Project.mentor_id == mentor_id,
                                                              Project.id.in_(db.select(ProjectMentor.project_id).where(ProjectMentor.mentor_id == mentor_id))))
    via_batch = (db.session.query(Project.id)
                 .join(BatchMentor, db.and_(BatchMentor.batch_id == Project.batch_id, BatchMentor.is_active.is_(True)))
                 .filter(BatchMentor.mentor_id == mentor_id, Project.mentor_id.is_(None)))
    return via_override.union(via_batch).count()
