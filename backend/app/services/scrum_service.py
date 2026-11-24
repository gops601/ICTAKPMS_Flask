"""Scrum board rules: who may do what, task CRUD, ordered moves, comments and history."""
from datetime import date

from app.extensions import db
from app.models import Project, ProjectStudent, ScrumBoard, ScrumTask, ScrumTaskAssignee, ScrumTaskComment, ScrumTaskHistory, Student
from app.models.base import utcnow
from app.models.scrum import TASK_PRIORITIES, TASK_STATUSES
from app.permissions.scope import student_profile
from app.services import lifecycle
from app.services.fields import parse_date
from app.services.notification_service import notify
from app.services.project_service import member_user_ids, mentor_user_ids
from app.utils.errors import AppError, Forbidden, NotFound

COLUMN_LABELS = {"backlog": "Backlog", "todo": "To Do", "in_progress": "In Progress",
                 "in_review": "In Review", "completed": "Completed"}
PRE_WORK_STATUSES = ("backlog", "todo")          # tasks that may still be deleted
MAX_TITLE, MAX_TEXT = 255, 5000


# ------------------------------------------------------------- permissions
def is_member(user, project):
    s = student_profile(user) if user.role_name == "student" else None
    return bool(s and any(pm.student_id == s.id for pm in project.members))


def _is_project_mentor(user, project):
    from app.services.evaluation_service import is_assigned_mentor
    return is_assigned_mentor(user, project)


def board_permissions(user, project):
    """What the user may do on this project's board, with a human reason when editing is blocked."""
    unlocked = lifecycle.ORDER[project.stage] >= lifecycle.ORDER["srs_approved"]
    finished = project.stage == "completed"
    reason = None
    if not unlocked:
        reason = "The Scrum board unlocks once your SRS is approved."
    elif finished:
        reason = "This project is completed; the board is read-only."
    role = user.role_name
    # Only the project's students and its mentors change the board; leads and admins are read-only.
    as_mentor = role == "mentor" or (role == "domain_lead" and _is_project_mentor(user, project))   # a lead who mentors this project
    editor = (role == "student" and is_member(user, project)) or as_mentor
    can_edit = editor and reason is None
    if role in ("domain_lead", "admin") and not as_mentor:
        reason = reason or "You have read-only access to this board."
    return {"can_create": can_edit, "can_edit": can_edit, "can_delete": can_edit, "can_move": can_edit,
            "can_comment": role in ("student", "mentor", "admin") or as_mentor, "reason": None if can_edit else reason}


def _require(perms, key, user):
    if not perms[key]:
        raise Forbidden(perms["reason"] or "You do not have permission to do that on this board")


# ---------------------------------------------------------------- helpers
def board_for(project):
    board = db.session.query(ScrumBoard).filter_by(project_id=project.id).first()
    if not board:  # projects created before boards existed; allocation normally creates it
        board = ScrumBoard(project_id=project.id)
        db.session.add(board)
        db.session.flush()
    return board


def get_task_or_404(task_id):
    task = db.session.get(ScrumTask, task_id)
    if not task or task.is_archived:
        raise NotFound("Task not found")
    return task


def _lock_project(project_id):
    return db.session.query(Project).filter_by(id=project_id).with_for_update().one()


def _hist(task, user, action, field=None, old=None, new=None):
    db.session.add(ScrumTaskHistory(task_id=task.id, user_id=user.id, action=action, field=field,
                                    old_value=None if old is None else str(old)[:500],
                                    new_value=None if new is None else str(new)[:500], created_at=utcnow()))


def is_overdue(task, today=None):
    return bool(task.due_date and task.status != "completed" and task.due_date < (today or date.today()))


def _assignee_name(student_id):
    s = db.session.get(Student, student_id) if student_id else None
    return s.user.name if s else None


def assignee_ids(task):
    """Everyone the task is assigned to (several are allowed), in the order they were added."""
    ids = [r[0] for r in db.session.query(ScrumTaskAssignee.student_id).filter_by(task_id=task.id).order_by(ScrumTaskAssignee.id)]
    if task.assigned_student_id and task.assigned_student_id not in ids:
        ids.insert(0, task.assigned_student_id)
    return ids


def _requested_assignees(project, data):
    """The assignee list in a request (None = not mentioned). Accepts assigned_student_ids, or the older single id."""
    if "assigned_student_ids" in data:
        raw = data["assigned_student_ids"] or []
    elif "assigned_student_id" in data:
        raw = [data["assigned_student_id"]] if data["assigned_student_id"] else []
    else:
        return None
    ids = list(dict.fromkeys(raw))
    members = {pm.student_id for pm in project.members}
    if any(i not in members for i in ids):
        raise AppError("Tasks can only be assigned to members of this project", 422,
                       {"assigned_student_ids": "Not a project member", "assigned_student_id": "Not a project member"})
    return ids


def _set_assignees(task, ids, project, user, log=True):
    old = assignee_ids(task)
    if old == ids:
        return
    db.session.query(ScrumTaskAssignee).filter_by(task_id=task.id).delete(synchronize_session=False)
    for i in ids:
        db.session.add(ScrumTaskAssignee(task_id=task.id, student_id=i))
    task.assigned_student_id = ids[0] if ids else None
    if log:
        _hist(task, user, "assigned", "assignee", ", ".join(_assignee_name(i) for i in old) or None,
              ", ".join(_assignee_name(i) for i in ids) or None)
    db.session.flush()
    db.session.expire(task, ["assignees"])
    added = [i for i in ids if i not in old]
    if added:
        users = {s.user_id for s in db.session.query(Student).filter(Student.id.in_(added))} - {user.id}
        notify(users, "task_assigned", "Task assigned to you", f"You were assigned “{task.title}” in “{project.title}”.", f"/scrum/{project.id}")


def _clean(data, existing=None):
    """Validate task fields; returns a dict containing only the fields that were supplied."""
    out, errors = {}, {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            errors["title"] = "Task title is required"
        elif len(title) > MAX_TITLE:
            errors["title"] = f"Title must be at most {MAX_TITLE} characters"
        out["title"] = title
    elif not existing:
        errors["title"] = "Task title is required"
    if "description" in data:
        desc = (data["description"] or "").strip()
        if len(desc) > MAX_TEXT:
            errors["description"] = f"Description must be at most {MAX_TEXT} characters"
        out["description"] = desc or None
    if "priority" in data:
        if data["priority"] not in TASK_PRIORITIES:
            errors["priority"] = f"Priority must be one of: {', '.join(TASK_PRIORITIES)}"
        out["priority"] = data["priority"]
    for key in ("start_date", "due_date"):
        if key in data:
            raw = data[key]
            try:
                out[key] = parse_date(raw) if raw not in (None, "") else None
            except ValueError as e:
                errors[key] = str(e)
    start = out.get("start_date", existing.start_date if existing else None)
    due = out.get("due_date", existing.due_date if existing else None)
    if start and due and due < start and "due_date" not in errors:
        errors["due_date"] = "Due date cannot be before the start date"
    if errors:
        raise AppError("Validation failed", 422, errors)
    return out


# ----------------------------------------------------------------- tasks
def _next_position(board_id, status):
    # Locking read: under MySQL REPEATABLE READ a plain SELECT after waiting on the project lock would
    # still see the transaction's older snapshot and hand out duplicate positions.
    last = (db.session.query(ScrumTask.position).filter_by(board_id=board_id, status=status, is_archived=False)
            .order_by(ScrumTask.position.desc()).with_for_update().first())
    return 0 if last is None else last[0] + 1


def create_task(project, data, user):
    perms = board_permissions(user, project)
    _require(perms, "can_create", user)
    project = _lock_project(project.id)
    clean = _clean(data)
    status = data.get("status") or "backlog"
    if status not in TASK_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(TASK_STATUSES)}", 422, {"status": "Invalid status"})
    assignees = _requested_assignees(project, data) or []
    board = board_for(project)
    task = ScrumTask(board_id=board.id, created_by=user.id, status=status,
                     position=_next_position(board.id, status), priority=clean.pop("priority", "medium"), **clean)
    if status == "completed":
        task.completed_at = utcnow()
    db.session.add(task)
    db.session.flush()
    _hist(task, user, "created", "status", None, status)
    _set_assignees(task, assignees, project, user, log=False)
    lifecycle.log_activity(project.id, user.id, "task.created", {"task_id": task.id, "title": task.title})
    return task


def update_task(task, project, data, user, expected_version=None):
    perms = board_permissions(user, project)
    _require(perms, "can_edit", user)
    _lock_project(project.id)
    db.session.refresh(task, with_for_update=True)       # latest committed row, not a cached/stale copy
    if expected_version is not None and expected_version != task.version:
        raise AppError("This task was changed by someone else. Reload and try again.", 409)
    clean = _clean(data, existing=task)
    new_assignees = _requested_assignees(project, data)
    if new_assignees is not None:
        _set_assignees(task, new_assignees, project, user)
    for field, value in clean.items():
        old = getattr(task, field)
        if old != value:
            _hist(task, user, "updated", field, old, value)
            setattr(task, field, value)
    task.version += 1
    return task


def move_task(task, project, status, position, user):
    perms = board_permissions(user, project)
    _require(perms, "can_move", user)
    if status not in TASK_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(TASK_STATUSES)}", 422, {"status": "Invalid status"})
    _lock_project(project.id)
    db.session.refresh(task, with_for_update=True)
    old_status = task.status

    def column(st):
        return (db.session.query(ScrumTask).filter_by(board_id=task.board_id, status=st, is_archived=False)
                .filter(ScrumTask.id != task.id).order_by(ScrumTask.position, ScrumTask.id).with_for_update().all())

    dest = column(status)
    index = len(dest) if position is None else max(0, min(position, len(dest)))
    dest.insert(index, task)
    task.status = status
    for i, t in enumerate(dest):
        t.position = i
    if old_status != status:
        for i, t in enumerate(column(old_status)):
            t.position = i
        _hist(task, user, "moved", "status", COLUMN_LABELS[old_status], COLUMN_LABELS[status])
        task.completed_at = utcnow() if status == "completed" else None
        lifecycle.log_activity(project.id, user.id, "task.moved", {"task_id": task.id, "from": old_status, "to": status})
        if status == "in_review":
            notify(mentor_user_ids(project), "task_in_review", "Task ready for review",
                   f"“{task.title}” moved to In Review in “{project.title}”.", f"/scrum/{project.id}")
    task.version += 1
    return task


def delete_task(task, project, user):
    perms = board_permissions(user, project)
    _require(perms, "can_delete", user)
    if task.status not in PRE_WORK_STATUSES:
        raise AppError("Only tasks that have not been started (Backlog / To Do) can be deleted", 409)
    task.is_archived = True      # soft delete keeps the history and activity trail intact
    _hist(task, user, "deleted")
    lifecycle.log_activity(project.id, user.id, "task.deleted", {"task_id": task.id, "title": task.title})


def add_comment(task, project, body, user):
    perms = board_permissions(user, project)
    if not perms["can_comment"]:
        raise Forbidden("You cannot comment on this board")
    body = (body or "").strip()
    if not body:
        raise AppError("Comment cannot be empty", 422, {"body": "Comment cannot be empty"})
    if len(body) > 2000:
        raise AppError("Comment is too long (max 2000 characters)", 422, {"body": "Too long"})
    comment = ScrumTaskComment(task_id=task.id, user_id=user.id, body=body)
    db.session.add(comment)
    db.session.flush()
    others = (member_user_ids(project) if user.role_name != "student" else mentor_user_ids(project)) - {user.id}
    notify(others, "task_comment", "New comment on a task", f"{user.name} commented on “{task.title}”.", f"/scrum/{project.id}")
    return comment


# ------------------------------------------------------------ serialisation
def task_to_dict(task, comment_count=None):
    from app.models import User
    u = db.session.get(User, task.created_by) if task.created_by else None
    return {
        "id": task.id, "title": task.title, "description": task.description, "priority": task.priority,
        "status": task.status, "position": task.position, "version": task.version,
        "assignees": [{"student_id": i, "name": _assignee_name(i)} for i in assignee_ids(task)],
        "assignee": {"student_id": task.assigned_student_id, "name": _assignee_name(task.assigned_student_id)} if task.assigned_student_id else None,
        "created_by": {"id": u.id, "name": u.name} if u else None,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat(), "is_overdue": is_overdue(task),
        "comment_count": comment_count if comment_count is not None else
        db.session.query(ScrumTaskComment).filter_by(task_id=task.id).count(),
    }


def task_detail(task):
    from app.models import User
    names = {}

    def name(uid):
        if uid not in names:
            u = db.session.get(User, uid) if uid else None
            names[uid] = u.name if u else "Unknown"
        return names[uid]

    comments = db.session.query(ScrumTaskComment).filter_by(task_id=task.id).order_by(ScrumTaskComment.id).all()
    history = db.session.query(ScrumTaskHistory).filter_by(task_id=task.id).order_by(ScrumTaskHistory.id.desc()).all()
    return {**task_to_dict(task, len(comments)),
            "comments": [{"id": c.id, "body": c.body, "user": name(c.user_id), "created_at": c.created_at.isoformat()} for c in comments],
            "history": [{"id": h.id, "action": h.action, "field": h.field, "old": h.old_value, "new": h.new_value,
                         "user": name(h.user_id), "at": h.created_at.isoformat()} for h in history]}


def stats_for(tasks):
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == "completed")
    return {"total": total, "completed": done, "overdue": sum(1 for t in tasks if is_overdue(t)),
            "completion_pct": round(done * 100 / total, 1) if total else 0.0,
            "by_status": {s: sum(1 for t in tasks if t.status == s) for s in TASK_STATUSES}}


def board_view(project, user, include_archived=False):
    board = board_for(project)
    q = db.session.query(ScrumTask).filter_by(board_id=board.id)
    if not include_archived:
        q = q.filter_by(is_archived=False)
    tasks = q.order_by(ScrumTask.position, ScrumTask.id).all()
    counts = dict(db.session.query(ScrumTaskComment.task_id, db.func.count(ScrumTaskComment.id))
                  .filter(ScrumTaskComment.task_id.in_([t.id for t in tasks] or [-1])).group_by(ScrumTaskComment.task_id).all())
    perms = board_permissions(user, project)
    return {
        "project": {"id": project.id, "title": project.title, "stage": project.stage,
                    "mentor_can_edit_board": project.mentor_can_edit_board},
        "permissions": perms,
        "members": [{"student_id": m.student_id, "name": m.student.user.name} for m in project.members],
        "columns": [{"status": s, "label": COLUMN_LABELS[s],
                     "tasks": [task_to_dict(t, counts.get(t.id, 0)) for t in tasks if t.status == s]} for s in TASK_STATUSES],
        "stats": stats_for(tasks),
    }
