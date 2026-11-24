from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Batch, Mentor, Project, ProjectMentor, ProjectStudent, Student, User
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_batch_access, ensure_project_access, scoped_projects
from app.schemas.project import (AllocationSchema, ProjectMembersSchema, ProjectMentorSchema, ProjectMentorsSchema, ProjectSettingsSchema, ReassignProblemSchema,
                                 ReopenSchema, TransitionSchema, project_to_dict, timeline)
from app.services import lifecycle, project_service
from app.utils.audit import audit
from app.utils.errors import AppError, Forbidden
from app.utils.responses import ok

bp = Blueprint("projects", __name__, url_prefix="/api", description="Projects, allocation and lifecycle")
SEC = [{"bearerAuth": []}]
MANAGERS = ("admin", "domain_lead")


@bp.post("/project-allocation")
@bp.doc(security=SEC, description="Allocate problem statements to students or teams. Mentors (own batches), domain leads and admins.")
@bp.arguments(AllocationSchema)
@roles_required(*MANAGERS, "mentor")
def allocate(data):
    user = current_user()
    batch = ensure_batch_access(user, data["batch_id"])
    projects = project_service.allocate(batch, data["items"], user, data["mentor_id"], data["start_date"], data["project_type"])
    audit(user.id, "project.allocate", "batch", batch.id, {"projects": len(projects)})
    db.session.commit()
    return ok([project_to_dict(p) for p in projects], f"{len(projects)} project(s) allocated", 201)


@bp.get("/projects")
@bp.doc(security=SEC)
@login_required
def list_projects():
    a = request.args
    q = scoped_projects(current_user())
    if a.get("batch_id", type=int):
        q = q.where(Project.batch_id == a.get("batch_id", type=int))
    if a.get("stage") in lifecycle.STAGES:
        q = q.where(Project.stage == a["stage"])
    if a.get("mentor_id", type=int):
        mid = a.get("mentor_id", type=int)
        q = q.where(db.or_(Project.mentor_id == mid, Project.id.in_(db.select(ProjectMentor.project_id).where(ProjectMentor.mentor_id == mid))))
    if a.get("project_type"):
        q = q.where(Project.project_type == a["project_type"])
    if a.get("domain_id", type=int):
        q = q.where(Project.batch_id.in_(db.select(Batch.id).where(Batch.domain_id == a.get("domain_id", type=int))))
    if a.get("q"):
        like = f"%{a['q']}%"
        member = (db.select(ProjectStudent.project_id).join(Student, Student.id == ProjectStudent.student_id)
                  .join(User, User.id == Student.user_id).where(db.or_(User.name.like(like), Student.registration_no.like(like))))
        q = q.where(db.or_(Project.title.like(like), Project.id.in_(member)))
    q = q.order_by(Project.created_at.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    items = [project_to_dict(p) for p in page.items]
    if a.get("delayed") in ("1", "true"):
        items = [i for i in items if i["is_delayed"]]  # derived value, filtered after computation
    return ok(items, meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.get("/projects/<int:project_id>")
@bp.doc(security=SEC)
@login_required
def get_project(project_id):
    user = current_user()
    return ok(project_to_dict(ensure_project_access(user, project_id), True, user.role_name))


@bp.get("/projects/<int:project_id>/timeline")
@bp.doc(security=SEC)
@login_required
def get_timeline(project_id):
    ensure_project_access(current_user(), project_id)
    return ok(timeline(project_id))


@bp.post("/projects/<int:project_id>/transition")
@bp.doc(security=SEC, description="Manual lifecycle steps only; SRS steps are performed by the SRS workflow.")
@bp.arguments(TransitionSchema)
@login_required
def transition(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    lifecycle.transition(project, data["to"], user, data.get("reason"))
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name), f"Project moved to {lifecycle.LABELS[project.stage]}")


@bp.post("/projects/<int:project_id>/close")
@bp.doc(security=SEC, description="The domain lead closes a completed project.")
@roles_required("domain_lead", "admin")
def close(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    lifecycle.close(project, user)
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name), "Project closed")


@bp.post("/projects/<int:project_id>/reopen")
@bp.doc(security=SEC, description="Domain lead (own domain) or admin reopens a completed/closed project to an earlier stage.")
@bp.arguments(ReopenSchema)
@roles_required("domain_lead", "admin")
def reopen(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    lifecycle.reopen(project, data["to"], user, data["reason"])
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name), "Project reopened")


@bp.put("/projects/<int:project_id>/mentors")
@bp.doc(security=SEC, description="Domain lead (own domain) or admin: set the project's mentors (one or several). Empty list = the batch's mentors.")
@bp.arguments(ProjectMentorsSchema)
@roles_required(*MANAGERS)
def set_mentors(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    project_service.set_project_mentors(project, data["mentor_ids"], user, data.get("reason"))
    audit(user.id, "project.mentors", "project", project.id, {"mentor_ids": data["mentor_ids"], "reason": data.get("reason")})
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name))


@bp.put("/projects/<int:project_id>/members")
@bp.doc(security=SEC, description="Change the team (students and their roles). Only the project's mentors, the domain lead and admins "
                                  "may; students cannot change their own group.")
@bp.arguments(ProjectMembersSchema)
@roles_required("mentor", "domain_lead", "admin")
def set_members(data, project_id):
    from app.services.evaluation_service import is_assigned_mentor
    user = current_user()
    project = ensure_project_access(user, project_id)
    if user.role_name == "mentor" and not is_assigned_mentor(user, project):
        raise Forbidden("Only a mentor of this project, the domain lead or an admin can change the team")
    project_service.set_project_members(project, data["members"], user, data.get("reason"))
    audit(user.id, "project.members", "project", project.id, {"students": [m["student_id"] for m in data["members"]]})
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name), "Team updated")


@bp.put("/projects/<int:project_id>/mentor")
@bp.doc(security=SEC)
@bp.arguments(ProjectMentorSchema)
@roles_required(*MANAGERS)
def set_mentor(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    project_service.set_project_mentor(project, data["mentor_id"], user, data.get("reason"))
    audit(user.id, "project.mentor", "project", project.id, {"mentor_id": data["mentor_id"], "reason": data.get("reason")})
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name))


@bp.delete("/projects/<int:project_id>")
@bp.doc(security=SEC, description="Admin only. Permanently deletes a project with its reviews, board, SRS and feedback.")
@roles_required("admin")
def delete_project(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    info = project_service.delete_project(project)
    audit(user.id, "project.delete", "project", project_id, info)
    db.session.commit()
    return ok(message=f"Project {info['code'] or info['title']} was deleted")


@bp.patch("/projects/<int:project_id>/settings")
@bp.doc(security=SEC)
@bp.arguments(ProjectSettingsSchema)
@roles_required(*MANAGERS)
def settings(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    project.mentor_can_edit_board = data["mentor_can_edit_board"]
    lifecycle.log_activity(project.id, user.id, "settings.mentor_board_edit", {"enabled": data["mentor_can_edit_board"]})
    audit(user.id, "project.settings", "project", project.id, data)
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name))


@bp.post("/projects/<int:project_id>/reassign-problem")
@bp.doc(security=SEC)
@bp.arguments(ReassignProblemSchema)
@roles_required(*MANAGERS)
def reassign_problem(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    project_service.reassign_problem(project, data["problem_statement_id"], user)
    audit(user.id, "project.reassign_problem", "project", project.id, data)
    db.session.commit()
    return ok(project_to_dict(project, True, user.role_name))
