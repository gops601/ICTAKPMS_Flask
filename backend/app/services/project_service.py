"""Project allocation, mentor assignment, progress and delay calculation."""
from datetime import date, timedelta

from app.extensions import db
from app.models import (Batch, BatchMentor, DomainLead, Mentor, ProblemStatement, Project, ProjectAssignment,
                        ProjectGithubRepository, ProjectMentor, ProjectReview, ProjectStudent, ScrumBoard, ScrumTask, Student,
                        SystemSetting)
from app.models.base import utcnow
from app.services import lifecycle, proposal_service
from app.services.metrics_service import DEFAULT_WEIGHTS, PROJECT_WEEKS, progress_weights, project_metrics, weeks_for  # noqa: F401
from app.services.fields import parse_date
from app.services.notification_service import domain_lead_user_ids, notify
from app.utils.errors import AppError, NotFound
from app.utils.ids import next_scoped_id

MAX_STUDENTS_PER_REQUEST = 200


# ------------------------------------------------------------------- lookups
def mentors_for_project(project):
    """Per-project override if set, otherwise the batch's active mentors."""
    ids = [r[0] for r in db.session.query(ProjectMentor.mentor_id).filter_by(project_id=project.id).order_by(ProjectMentor.id)]
    if project.mentor_id and project.mentor_id not in ids:
        ids.insert(0, project.mentor_id)
    if ids:
        found = {m.id: m for m in db.session.query(Mentor).filter(Mentor.id.in_(ids))}
        return [found[i] for i in ids if i in found]
    q = (db.session.query(Mentor).join(BatchMentor, BatchMentor.mentor_id == Mentor.id)
         .filter(BatchMentor.batch_id == project.batch_id, BatchMentor.is_active.is_(True)))
    return q.all()


def mentor_user_ids(project):
    return {m.user_id for m in mentors_for_project(project)}


def member_user_ids(project):
    return {pm.student.user_id for pm in project.members}


def get_project_or_404(project_id):
    p = db.session.get(Project, project_id)
    if not p:
        raise NotFound("Project not found")
    return p


def _eligible_batch_mentor(batch, mentor_id):
    link = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=mentor_id, is_active=True).first()
    if not link:
        raise AppError("That mentor is not assigned to this batch", 422, {"mentor_id": "Not a mentor of this batch"})
    return link.mentor


# ---------------------------------------------------------------- allocation
def clean_project_type(batch, project_type):
    """Academic OU projects must say what kind they are; every other OU has no project type."""
    from app.models.project import ACADEMIC_OU_CODE, PROJECT_TYPES
    if batch.ou.code != ACADEMIC_OU_CODE:
        return None
    if not project_type:
        raise AppError("Choose the project type (Add-on Course, Summer Internship or Other)", 422,
                       {"project_type": "Project type is required for Academic OU projects"})
    if project_type not in PROJECT_TYPES:
        raise AppError("Project type must be one of: " + ", ".join(PROJECT_TYPES.values()), 422,
                       {"project_type": "Invalid project type"})
    return project_type


def allocate(batch, items, actor, mentor_id=None, start_date=None, project_type=None):
    """Allocate problem statements to students/teams. All-or-nothing; returns the created projects.

    items: [{"problem_statement_id": int, "student_ids": [int], "team": bool}]
    A multi-student item becomes one team project when team=True, otherwise one project per student.
    """
    if batch.status != "active":
        raise AppError("Projects can only be allocated in an active batch", 409)
    if not batch.domain_id:
        raise AppError("The batch has no domain assigned", 409)
    if not items:
        raise AppError("Select at least one student", 422)

    start = parse_date(start_date) if start_date else (batch.project_start_date or date.today())
    end = batch.project_end_date  # set by the domain lead; otherwise the default project length applies
    if end and end <= start:
        raise AppError("The project start date must be before the batch's project end date", 422,
                       {"start_date": f"Must be before {end.isoformat()}"})
    mentor = _eligible_batch_mentor(batch, mentor_id) if mentor_id else None
    project_type = clean_project_type(batch, project_type)

    all_ids = [sid for it in items for sid in it["student_ids"]]
    if len(all_ids) != len(set(all_ids)):
        raise AppError("A student appears more than once in this request", 422)
    if len(all_ids) > MAX_STUDENTS_PER_REQUEST:
        raise AppError(f"At most {MAX_STUDENTS_PER_REQUEST} students per request", 422)

    students = {s.id: s for s in db.session.query(Student).filter(Student.id.in_(all_ids or [-1])).all()}
    problems = []
    for sid in all_ids:
        s = students.get(sid)
        if not s or s.batch_id != batch.id:
            problems.append(f"Student #{sid} is not in this batch")
    taken = (db.session.query(Student).join(ProjectStudent, ProjectStudent.student_id == Student.id)
             .filter(Student.id.in_(all_ids or [-1])).all())
    problems += [f"{t.user.name} already has a project" for t in taken]
    if problems:
        raise AppError("Allocation not possible: " + "; ".join(problems[:5]), 422, {"students": problems})

    ps_cache = {}
    created = []
    for it in items:
        ps = ps_cache.get(it["problem_statement_id"]) or db.session.get(ProblemStatement, it["problem_statement_id"])
        ps_cache[it["problem_statement_id"]] = ps
        if not ps:
            raise AppError("Problem statement not found", 422, {"problem_statement_id": "Not found"})
        if ps.domain_id != batch.domain_id:
            raise AppError(f"'{ps.ps_code}' belongs to a different domain than this batch", 422)
        if ps.status != "active":
            raise AppError(f"'{ps.ps_code}' is inactive and cannot be allocated", 422)
        if ps.approval_status != "approved":
            raise AppError(f"'{ps.ps_code}' has not been approved by a mentor yet and cannot be allocated", 422)
        groups = [it["student_ids"]] if it.get("team") else [[sid] for sid in it["student_ids"]]
        for group in groups:
            created.append(_create_project(batch, ps, [students[i] for i in group], actor, mentor, start, end, project_type))

    db.session.flush()
    proposal_service.withdraw_pending(all_ids)
    _notify_allocation(batch, created)
    return created


def _create_project(batch, ps, members, actor, mentor, start, end=None, project_type=None):
    project = Project(code=next_scoped_id(batch.ou.code, batch.mode, Project.code),
                      batch_id=batch.id, problem_statement_id=ps.id, mentor_id=mentor.id if mentor else None,
                      title=ps.title, stage="allocated", start_date=start, project_type=project_type,
                      target_end_date=end or start + timedelta(weeks=weeks_for(batch.mode)))
    db.session.add(project)
    db.session.flush()
    for i, s in enumerate(members):
        db.session.add(ProjectStudent(project_id=project.id, student_id=s.id, is_lead=(i == 0 and len(members) > 1)))
    db.session.add(ProjectAssignment(project_id=project.id, assignment_type="allocation",
                                     mentor_id=mentor.id if mentor else None, assigned_by=actor.id,
                                     notes=f"Allocated {ps.ps_code}"))
    db.session.add(ScrumBoard(project_id=project.id))
    for week in range(1, weeks_for(batch.mode) + 1):  # review schedule (3 for offline batches, 4 for online); criteria/scores are added by the mentor later
        db.session.add(ProjectReview(project_id=project.id, week_no=week, due_date=start + timedelta(weeks=week),
                                     status="pending"))
    lifecycle.record_initial(project, actor.id)
    return project


def _notify_allocation(batch, projects):
    db.session.flush()
    for p in projects:
        db.session.refresh(p)
        notify(member_user_ids(p), "project_allocated", "Project allocated",
               f"You have been allocated “{p.title}”. Start preparing your SRS.", "/student/project")
        notify(mentor_user_ids(p), "project_allocated", "New project allocated",
               f"“{p.title}” was allocated in batch {batch.code}.", f"/projects/{p.id}")
    notify(domain_lead_user_ids(batch.domain_id), "projects_allocated", "Projects allocated",
           f"{len(projects)} project(s) were allocated in batch {batch.code}.", f"/lead/batches/{batch.id}")


def reassign_problem(project, ps_id, actor):
    if project.stage not in ("allocated", "srs_preparation"):
        raise AppError("The problem statement can only be changed before an SRS is submitted", 409)
    ps = db.session.get(ProblemStatement, ps_id)
    if not ps or ps.domain_id != project.batch.domain_id:
        raise AppError("Choose an active problem statement from this batch's domain", 422)
    if ps.status != "active":
        raise AppError(f"'{ps.ps_code}' is inactive and cannot be allocated", 422)
    if ps.approval_status != "approved":
        raise AppError(f"'{ps.ps_code}' has not been approved by a mentor yet and cannot be allocated", 422)
    if ps.id == project.problem_statement_id:
        raise AppError("That problem statement is already allocated", 409)
    old = project.problem_statement
    project.problem_statement_id, project.title = ps.id, ps.title
    db.session.add(ProjectAssignment(project_id=project.id, assignment_type="reassignment", assigned_by=actor.id,
                                     notes=f"Problem statement changed {old.ps_code} -> {ps.ps_code}"))
    lifecycle.log_activity(project.id, actor.id, "problem_statement.changed", {"from": old.ps_code, "to": ps.ps_code})
    db.session.flush()
    db.session.refresh(project)
    notify(member_user_ids(project), "project_allocated", "Problem statement changed",
           f"Your project is now “{ps.title}”.", "/student/project")
    return project


# -------------------------------------------------------------- mentor ops
def _any_active_mentor(mentor_id):
    mentor = db.session.get(Mentor, mentor_id)
    if not mentor:
        raise NotFound("Mentor not found")
    if not mentor.user.is_active:
        raise AppError("That mentor's account is inactive", 422, {"mentor_id": "Mentor is inactive"})
    return mentor


def _store_mentors(project, mentor_ids):
    """Persist the explicit mentor list; Project.mentor_id mirrors the first one (None = fall back to the batch)."""
    ids = list(dict.fromkeys(mentor_ids))
    db.session.query(ProjectMentor).filter_by(project_id=project.id).delete(synchronize_session=False)
    for i in ids:
        db.session.add(ProjectMentor(project_id=project.id, mentor_id=i))
    project.mentor_id = ids[0] if ids else None


def projects_with_mentor(batch_id, mentor_id):
    extra = db.select(ProjectMentor.project_id).where(ProjectMentor.mentor_id == mentor_id)
    return (db.session.query(Project).filter(Project.batch_id == batch_id)
            .filter(db.or_(Project.mentor_id == mentor_id, Project.id.in_(extra))).all())


def set_project_mentors(project, mentor_ids, actor, reason=None):
    """Assign one or more mentors to a project (replaces the list); an empty list falls back to the batch's mentors.

    Domain leads choose among the batch's mentors; an administrator may choose any active mentor. Mentors who
    were removed are told, new ones are told they were assigned, and the students are told who mentors them.
    """
    previous = mentor_user_ids(project)
    ids = list(dict.fromkeys(mentor_ids or []))
    mentors = [_any_active_mentor(i) if actor.role_name == "admin" else _eligible_batch_mentor(project.batch, i) for i in ids]
    reason = (reason or "").strip() or None
    _store_mentors(project, [m.id for m in mentors])
    names = ", ".join(m.user.name for m in mentors)
    note = (f"Mentors set: {names}" if mentors else "Mentor override cleared") + (f" ({reason})" if reason else "")
    db.session.add(ProjectAssignment(project_id=project.id, assignment_type="reassignment" if previous else "mentor_assignment",
                                     mentor_id=project.mentor_id, assigned_by=actor.id, notes=note[:500]))
    lifecycle.log_activity(project.id, actor.id, "mentor.changed", {"mentor_ids": [m.id for m in mentors], "reason": reason})
    db.session.flush()
    db.session.expire(project)
    now = mentor_user_ids(project)
    notify(previous - now, "project_unassigned", "Project reassigned",
           f"“{project.title}” was reassigned to other mentor(s)." + (f" Reason: {reason}" if reason else ""), None)
    notify(member_user_ids(project), "mentor_assigned", "Mentor assigned",
           f"{names} {'is' if len(mentors) == 1 else 'are'} now mentoring “{project.title}”." if mentors else "Your project mentor changed.",
           "/student/project")
    notify(now - previous, "project_allocated", "Project assigned to you", f"You were assigned “{project.title}”.", f"/projects/{project.id}")
    return project


def set_project_mentor(project, mentor_id, actor, reason=None):
    """Single-mentor form kept for older callers."""
    return set_project_mentors(project, [mentor_id] if mentor_id else [], actor, reason)


def assign_batch_mentor(batch, mentor, actor):
    if not mentor.user.is_active:
        raise AppError("That mentor's account is inactive", 422)
    if mentor.domain_id and batch.domain_id and mentor.domain_id != batch.domain_id:
        leads_it = db.session.query(DomainLead.id).filter_by(user_id=mentor.user_id, domain_id=batch.domain_id).first()
        if not leads_it:                      # a domain lead is a mentor of every domain they lead
            raise AppError("That mentor belongs to a different domain", 422)
    link = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=mentor.id).first()
    if link and link.is_active:
        raise AppError("That mentor is already assigned to this batch", 409)
    if link:
        link.is_active, link.assigned_by = True, actor.id
    else:
        db.session.add(BatchMentor(batch_id=batch.id, mentor_id=mentor.id, assigned_by=actor.id))
    db.session.flush()
    notify({mentor.user_id}, "batch_assigned", "New batch assigned",
           f"You have been assigned to batch {batch.code} – {batch.name}.", f"/mentor/batches/{batch.id}")
    # students hear about a mentor only once they have a project: before that, nobody is "their" mentor yet
    students = (db.session.query(Student).filter_by(batch_id=batch.id)
                .filter(Student.id.in_(db.select(ProjectStudent.student_id))).all())
    notify({s.user_id for s in students}, "mentor_assigned", "Mentor assigned",
           f"{mentor.user.name} is now a mentor for your batch.", "/student/project")


def remove_batch_mentor(batch, mentor):
    link = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=mentor.id, is_active=True).first()
    if not link:
        raise NotFound("That mentor is not assigned to this batch")
    link.is_active = False
    # Project-level overrides pointing at the removed mentor fall back to the batch's mentors.
    for p in projects_with_mentor(batch.id, mentor.id):
        _store_mentors(p, [m.id for m in mentors_for_project(p) if m.id != mentor.id])


def reassign_batch_mentor(batch, from_mentor, to_mentor, actor):
    """Atomically swap a mentor for another across the batch (including project overrides)."""
    if from_mentor.id == to_mentor.id:
        raise AppError("Choose a different mentor", 422)
    link = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=from_mentor.id, is_active=True).first()
    if not link:
        raise NotFound("The current mentor is not assigned to this batch")
    overridden = projects_with_mentor(batch.id, from_mentor.id)
    link.is_active = False
    existing = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=to_mentor.id, is_active=True).first()
    if not existing:
        assign_batch_mentor(batch, to_mentor, actor)
    for p in overridden:
        _store_mentors(p, [to_mentor.id if m.id == from_mentor.id else m.id for m in mentors_for_project(p)])
        db.session.add(ProjectAssignment(project_id=p.id, assignment_type="reassignment", mentor_id=to_mentor.id,
                                         assigned_by=actor.id, notes=f"Mentor reassigned from {from_mentor.user.name}"))
        lifecycle.log_activity(p.id, actor.id, "mentor.changed", {"from": from_mentor.id, "to": to_mentor.id})
    db.session.flush()
    notify({from_mentor.user_id}, "batch_unassigned", "Batch reassigned",
           f"You are no longer assigned to batch {batch.code}.", None)


MAX_TEAM_SIZE = 12


def set_project_members(project, members, actor, reason=None):
    """Replace the project's team and roles. Only mentors of the project, the domain lead and admins call this (the route checks).

    members: [{"student_id", "role", "is_lead"}]. Students must belong to the project's batch and be free (or already in this
    project). Removed students lose their Scrum assignments on this project; added and removed students are notified.
    """
    from app.models import ScrumBoard, ScrumTask, ScrumTaskAssignee
    ids, roles, lead = [], {}, None
    for m in members:
        sid = m["student_id"]
        if sid in roles:
            raise AppError("A student appears more than once", 422, {"members": "Duplicate student"})
        ids.append(sid)
        roles[sid] = (m.get("role") or "").strip()[:60] or None
        if m.get("is_lead") and lead is None:
            lead = sid
    if not ids:
        raise AppError("A project needs at least one student", 422, {"members": "Select at least one student"})
    if len(ids) > MAX_TEAM_SIZE:
        raise AppError(f"A team can have at most {MAX_TEAM_SIZE} students", 422, {"members": "Too many students"})
    students = {s.id: s for s in db.session.query(Student).filter(Student.id.in_(ids)).all()}
    current = {pm.student_id: pm for pm in project.members}
    problems = []
    for sid in ids:
        s = students.get(sid)
        if not s or s.batch_id != project.batch_id:
            problems.append(f"Student #{sid} is not in this batch")
        elif sid not in current and db.session.query(ProjectStudent.id).filter_by(student_id=sid).first():
            problems.append(f"{s.user.name} already has a project")
    if problems:
        raise AppError("Team not changed: " + "; ".join(problems[:4]), 422, {"members": problems})
    if len(ids) > 1 and lead is None:
        lead = ids[0]
    removed = [sid for sid in current if sid not in roles]
    added = [sid for sid in ids if sid not in current]
    for sid in removed:
        db.session.delete(current[sid])
    board = db.session.query(ScrumBoard).filter_by(project_id=project.id).first()
    if removed and board:                                   # drop their task assignments on this board
        task_ids = [t[0] for t in db.session.query(ScrumTask.id).filter_by(board_id=board.id)]
        if task_ids:
            db.session.query(ScrumTaskAssignee).filter(ScrumTaskAssignee.task_id.in_(task_ids),
                                                       ScrumTaskAssignee.student_id.in_(removed)).delete(synchronize_session=False)
            db.session.query(ScrumTask).filter(ScrumTask.id.in_(task_ids), ScrumTask.assigned_student_id.in_(removed)).update(
                {"assigned_student_id": None}, synchronize_session=False)
    for sid in ids:
        pm = current.get(sid)
        if pm is None:
            pm = ProjectStudent(project_id=project.id, student_id=sid)
            db.session.add(pm)
        pm.role, pm.is_lead = roles[sid], (len(ids) > 1 and sid == lead)
    db.session.flush()
    db.session.expire(project)
    reason = (reason or "").strip() or None
    db.session.add(ProjectAssignment(project_id=project.id, assignment_type="reassignment", assigned_by=actor.id,
                                     notes=("Team changed" + (f": {reason}" if reason else ""))[:500]))
    lifecycle.log_activity(project.id, actor.id, "team.changed", {"added": added, "removed": removed, "reason": reason})
    notify({students[s].user_id for s in added}, "project_allocated", "You were added to a project",
           f"You are now part of “{project.title}”.", "/student/project")
    gone = db.session.query(Student).filter(Student.id.in_(removed or [-1])).all()
    notify({s.user_id for s in gone}, "project_unassigned", "Removed from a project",
           f"You are no longer part of “{project.title}”." + (f" Reason: {reason}" if reason else ""), None)
    return project


def transfer_mentor(from_mentor, to_mentor, batches, actor):
    """Take a mentor off every given batch (and the projects they mentor there), handing the work to `to_mentor`.

    `to_mentor=None` simply removes the mentor; their projects fall back to the batch's remaining mentors. Only the
    batches passed in are touched, so a domain lead never reaches outside their own domains. Returns a summary.
    """
    if to_mentor is not None:
        if from_mentor.id == to_mentor.id:
            raise AppError("Choose a different mentor", 422)
        if not to_mentor.user.is_active:
            raise AppError("That mentor's account is inactive", 422)
    batches_done = projects_done = 0
    for batch in batches:
        on_batch = db.session.query(BatchMentor).filter_by(batch_id=batch.id, mentor_id=from_mentor.id, is_active=True).first()
        affected = projects_with_mentor(batch.id, from_mentor.id)
        if not on_batch and not affected:
            continue
        if on_batch and to_mentor is not None:
            reassign_batch_mentor(batch, from_mentor, to_mentor, actor)           # also swaps the project overrides
        elif on_batch:
            remove_batch_mentor(batch, from_mentor)
        else:                                                                    # project-only assignment (admin override)
            for p in affected:
                _store_mentors(p, list(dict.fromkeys(to_mentor.id if m.id == from_mentor.id else m.id
                                                     for m in mentors_for_project(p)))
                               if to_mentor else [m.id for m in mentors_for_project(p) if m.id != from_mentor.id])
        batches_done += 1 if on_batch else 0
        projects_done += len(affected)
        if not on_batch or to_mentor is None:
            for p in affected:
                db.session.add(ProjectAssignment(project_id=p.id, assignment_type="reassignment",
                                                 mentor_id=to_mentor.id if to_mentor else None, assigned_by=actor.id,
                                                 notes=f"Mentor {from_mentor.user.name} " + (f"replaced by {to_mentor.user.name}" if to_mentor else "removed")))
                lifecycle.log_activity(p.id, actor.id, "mentor.changed", {"from": from_mentor.id, "to": to_mentor.id if to_mentor else None})
    if to_mentor is not None and projects_done:
        notify({to_mentor.user_id}, "project_allocated", "Projects assigned to you",
               f"{projects_done} project(s) were handed over to you from {from_mentor.user.name}.", None)
    db.session.flush()
    return {"batches": batches_done, "projects": projects_done}


# --------------------------------------------------------------- progress
# Progress and delay are computed in metrics_service (one implementation, bulk-capable); these
# single-project helpers delegate so every screen agrees.
def compute_progress(project):
    """Weighted completion percentage (SRS, GitHub, Scrum, reviews, final sign-off)."""
    return project_metrics([project])[project.id]["progress"]


def delay_reasons(project, today=None):
    """Why a project counts as delayed (empty list = on track). Completed projects are never delayed."""
    return project_metrics([project], today)[project.id]["delay_reasons"]


# ---------------------------------------------------------------- deletion
def delete_project(project):
    """Permanently remove a project and everything hanging off it (admin only, enforced by the route)."""
    from app.models import (MentorFeedback, ProjectActivityLog, ProjectLifecycleTransition, ScrumTask, ScrumTaskComment,
                            ScrumTaskAssignee, ScrumTaskHistory, SrsSubmission)
    from app.services import file_service
    info = {"code": project.code, "title": project.title, "stage": project.stage}
    pid = project.id
    srs_files = [sub.file for sub in db.session.query(SrsSubmission).filter_by(project_id=pid).all()]
    for sub in db.session.query(SrsSubmission).filter_by(project_id=pid).all():
        db.session.delete(sub)               # review history cascades
    board = db.session.query(ScrumBoard).filter_by(project_id=pid).first()
    if board:
        task_ids = [t.id for t in db.session.query(ScrumTask.id).filter_by(board_id=board.id).all()]
        if task_ids:
            db.session.query(ScrumTaskAssignee).filter(ScrumTaskAssignee.task_id.in_(task_ids)).delete(synchronize_session=False)
            db.session.query(ScrumTaskComment).filter(ScrumTaskComment.task_id.in_(task_ids)).delete(synchronize_session=False)
            db.session.query(ScrumTaskHistory).filter(ScrumTaskHistory.task_id.in_(task_ids)).delete(synchronize_session=False)
            db.session.query(ScrumTask).filter(ScrumTask.id.in_(task_ids)).delete(synchronize_session=False)
        db.session.delete(board)
    for review in db.session.query(ProjectReview).filter_by(project_id=pid).all():
        db.session.delete(review)            # criteria, scores, revisions, remarks, date requests cascade
    for model in (ProjectGithubRepository, ProjectAssignment, ProjectMentor, MentorFeedback, ProjectLifecycleTransition, ProjectActivityLog):
        db.session.query(model).filter_by(project_id=pid).delete(synchronize_session=False)
    db.session.flush()
    db.session.delete(project)               # members cascade
    db.session.flush()
    for f in srs_files:
        file_service.delete_file(f)
    return info
