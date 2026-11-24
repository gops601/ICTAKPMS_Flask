from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.services.domain_sync_service import mentor_in_domains
from app.models import BatchMentor, Mentor, Project, ProjectMentor, ProjectStudent, Student, User
from app.permissions import current_user, roles_required
from app.permissions.scope import lead_domain_ids, scoped_batches  # noqa: F401
from app.schemas.org import CredentialsSchema, StudentCreateSchema, mentor_to_dict, student_to_dict
from app.schemas.project import TransferMentorSchema
from app.services import project_service, user_service
from app.utils.audit import audit
from app.utils.errors import NotFound
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


@bp.post("/mentors/<int:mentor_id>/transfer")
@bp.doc(security=SEC, description="Remove a mentor from the batches/projects the caller manages, handing them to another "
                                  "mentor (to_mentor_id) or just removing them (null). Domain leads: their own domains only.")
@bp.arguments(TransferMentorSchema)
@roles_required("admin", "domain_lead")
def transfer_mentor(data, mentor_id):
    user = current_user()
    mentor = db.session.get(Mentor, mentor_id)
    if not mentor:
        raise NotFound("Mentor not found")
    target = None
    if data["to_mentor_id"] is not None:
        target = db.session.get(Mentor, data["to_mentor_id"])
        if not target:
            raise NotFound("The replacement mentor was not found")
    in_scope = {b.id: b for b in db.session.scalars(scoped_batches(user))}
    on = {r[0] for r in db.session.query(BatchMentor.batch_id).filter_by(mentor_id=mentor.id, is_active=True)}
    extra = {r[0] for r in db.session.query(Project.batch_id).filter(db.or_(
        Project.mentor_id == mentor.id, Project.id.in_(db.select(ProjectMentor.project_id).where(ProjectMentor.mentor_id == mentor.id))))}
    batches = [in_scope[i] for i in sorted(on | extra) if i in in_scope]
    summary = project_service.transfer_mentor(mentor, target, batches, user)
    audit(user.id, "mentor.transfer", "mentor", mentor.id, {"to": data["to_mentor_id"], **summary})
    db.session.commit()
    skipped = len((on | extra) - set(in_scope))
    who = f"to {target.user.name}" if target else "(removed)"
    return ok({**summary, "skipped_batches": skipped},
              f"{mentor.user.name}: {summary['batches']} batch(es) and {summary['projects']} project(s) moved {who}"
              + (f"; {skipped} batch(es) outside your domains were left unchanged" if skipped else ""))


@bp.get("/my/mentors")
@bp.doc(security=SEC, description="Names of the mentors of the student's project(s); empty until a project is allocated. Names only.")
@roles_required("student")
def my_mentors():
    from app.permissions.scope import student_profile
    s = student_profile(current_user())
    if not s:
        return ok([])
    found = {}                                      # only the mentors of the student's own project(s), never the whole batch
    for p in db.session.query(Project).join(ProjectStudent, ProjectStudent.project_id == Project.id).filter(ProjectStudent.student_id == s.id):
        for m in project_service.mentors_for_project(p):
            found.setdefault(m.id, m)
    rows = sorted((m for m in found.values() if m.user.is_active), key=lambda m: m.user.name)
    return ok([{"id": m.id, "name": m.user.name} for m in rows])


def _workload(mentor_id):
    """Projects overseen via a per-project override, or via an active batch assignment without an override."""
    via_override = db.session.query(Project.id).filter(db.or_(Project.mentor_id == mentor_id,
                                                              Project.id.in_(db.select(ProjectMentor.project_id).where(ProjectMentor.mentor_id == mentor_id))))
    via_batch = (db.session.query(Project.id)
                 .join(BatchMentor, db.and_(BatchMentor.batch_id == Project.batch_id, BatchMentor.is_active.is_(True)))
                 .filter(BatchMentor.mentor_id == mentor_id, Project.mentor_id.is_(None)))
    return via_override.union(via_batch).count()
