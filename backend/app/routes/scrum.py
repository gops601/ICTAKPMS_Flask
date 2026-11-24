import io

from flask import request, send_file
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models import Project, ScrumBoard, ScrumTask
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_project_access, scoped_projects
from app.services import scrum_service as svc
from app.utils.audit import audit
from app.utils.errors import AppError, NotFound
from app.utils.responses import ok

bp = Blueprint("scrum", __name__, url_prefix="/api/scrum", description="Scrum boards and tasks")
SEC = [{"bearerAuth": []}]


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class TaskCreateSchema(_Base):
    title = fields.String(required=True, validate=validate.Length(min=1, max=300))
    description = fields.String(allow_none=True)
    priority = fields.String()
    status = fields.String()
    assigned_student_id = fields.Integer(allow_none=True)
    assigned_student_ids = fields.List(fields.Integer())
    start_date = fields.String(allow_none=True)
    due_date = fields.String(allow_none=True)


class TaskUpdateSchema(_Base):
    title = fields.String(validate=validate.Length(min=1, max=300))
    description = fields.String(allow_none=True)
    priority = fields.String()
    assigned_student_id = fields.Integer(allow_none=True)
    assigned_student_ids = fields.List(fields.Integer())
    start_date = fields.String(allow_none=True)
    due_date = fields.String(allow_none=True)
    version = fields.Integer()


class MoveSchema(_Base):
    status = fields.String(required=True)
    position = fields.Integer(allow_none=True, load_default=None)


class CommentSchema(_Base):
    body = fields.String(required=True)


def _task_and_project(task_id):
    """Resolve a task the current user can see; hides existence otherwise."""
    task = svc.get_task_or_404(task_id)
    project = db.session.get(Project, db.session.get(ScrumBoard, task.board_id).project_id)
    ensure_project_access(current_user(), project.id)
    return task, project


@bp.get("/projects/<int:project_id>/board")
@bp.doc(security=SEC)
@login_required
def get_board(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    db.session.commit()   # board_for may create a missing board
    return ok(svc.board_view(project, user))


@bp.post("/projects/<int:project_id>/tasks")
@bp.doc(security=SEC)
@bp.arguments(TaskCreateSchema)
@login_required
def create_task(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    task = svc.create_task(project, data, user)
    db.session.commit()
    return ok(svc.task_detail(task), "Task created", 201)


@bp.get("/projects/<int:project_id>/tasks/template")
@bp.doc(security=SEC, description="Fill-in template (xlsx or csv) for the weekly bulk task upload.")
@login_required
def tasks_template(project_id):
    project = ensure_project_access(current_user(), project_id)
    fmt = request.args.get("format", "xlsx")
    if fmt not in ("xlsx", "csv"):
        raise AppError("format must be xlsx or csv", 422)
    content, mime = svc.bulk_template(project, fmt)
    return send_file(io.BytesIO(content), mimetype=mime, as_attachment=True, download_name=f"scrum_tasks_template.{fmt}")


@bp.post("/projects/<int:project_id>/tasks/bulk")
@bp.doc(security=SEC, description="Upload the filled weekly template (multipart field 'file'). All rows are checked first; "
                                  "if any row is invalid nothing is created and the errors are returned.")
@login_required
def bulk_tasks(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise AppError("Choose a file to upload", 422)
    result = svc.bulk_create_tasks(project, upload.filename, upload.read(), user)
    if result["created"]:
        audit(user.id, "task.bulk_create", "project", project.id, {"count": result["created"]})
    db.session.commit()
    return ok({**result, "board": svc.board_view(project, user)},
              f"{result['created']} task(s) added" if result["created"] else "No tasks were added: fix the rows listed and upload again")


@bp.get("/tasks/<int:task_id>")
@bp.doc(security=SEC)
@login_required
def get_task(task_id):
    task, _ = _task_and_project(task_id)
    return ok(svc.task_detail(task))


@bp.put("/tasks/<int:task_id>")
@bp.doc(security=SEC)
@bp.arguments(TaskUpdateSchema)
@login_required
def update_task(data, task_id):
    task, project = _task_and_project(task_id)
    version = data.pop("version", None)
    svc.update_task(task, project, data, current_user(), version)
    db.session.commit()
    return ok(svc.task_detail(task))


@bp.patch("/tasks/<int:task_id>/move")
@bp.doc(security=SEC, description="Move a task to a column/position (drag and drop).")
@bp.arguments(MoveSchema)
@login_required
def move_task(data, task_id):
    task, project = _task_and_project(task_id)
    svc.move_task(task, project, data["status"], data["position"], current_user())
    db.session.commit()
    return ok(svc.board_view(project, current_user()), "Task moved")


@bp.delete("/tasks/<int:task_id>")
@bp.doc(security=SEC)
@login_required
def delete_task(task_id):
    task, project = _task_and_project(task_id)
    user = current_user()
    svc.delete_task(task, project, user)
    audit(user.id, "task.delete", "scrum_task", task.id, {"project_id": project.id})
    db.session.commit()
    return ok(svc.board_view(project, user), "Task deleted")


@bp.post("/tasks/<int:task_id>/comments")
@bp.doc(security=SEC)
@bp.arguments(CommentSchema)
@login_required
def add_comment(data, task_id):
    task, project = _task_and_project(task_id)
    svc.add_comment(task, project, data["body"], current_user())
    db.session.commit()
    return ok(svc.task_detail(task), "Comment added", 201)


@bp.get("/overview")
@bp.doc(security=SEC, description="Board statistics for every project in the caller's scope (monitoring).")
@roles_required("mentor", "domain_lead", "admin")
def overview():
    a = request.args
    q = scoped_projects(current_user())
    if a.get("started") in ("1", "true"):   # only projects whose board is unlocked
        q = q.where(Project.stage.in_(["srs_approved", "implementation", "final_evaluation", "completed"]))
    if a.get("batch_id", type=int):
        q = q.where(Project.batch_id == a.get("batch_id", type=int))
    q = q.order_by(Project.id)
    page = db.paginate(q, page=a.get("page", 1, type=int), per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    items = []
    for p in page.items:
        board = db.session.query(ScrumBoard).filter_by(project_id=p.id).first()
        tasks = db.session.query(ScrumTask).filter_by(board_id=board.id, is_archived=False).all() if board else []
        latest = max([t.updated_at for t in tasks], default=None)
        items.append({"project_id": p.id, "title": p.title, "stage": p.stage, "stage_label": svc.lifecycle.LABELS[p.stage],
                      "batch": {"id": p.batch.id, "code": p.batch.code},
                      "members": [m.student.user.name for m in p.members],
                      "stats": svc.stats_for(tasks), "last_activity": latest.isoformat() if latest else None})
    delayed_only = a.get("overdue") in ("1", "true")
    if delayed_only:
        items = [i for i in items if i["stats"]["overdue"] > 0]
    return ok(items, meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})
