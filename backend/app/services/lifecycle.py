"""Project lifecycle state machine.

`Project.stage` may only be changed through `transition()` / `reopen()` in this module. Every change
is timestamped (project_lifecycle_transitions) and mirrored in the activity log.

Weekly reviews are *not* stages: they are independent records (project_reviews). The stage machine
only gates the coarse milestones (SRS approval, implementation, final evaluation, completion).
"""
from app.extensions import db
from app.models import Project, ProjectActivityLog, ProjectLifecycleTransition, ProjectReview
from app.models.base import utcnow
from app.services.notification_service import domain_lead_user_ids, notify
from app.utils.audit import audit
from app.utils.errors import AppError, Forbidden

STAGES = ["allocated", "srs_preparation", "srs_submitted", "srs_under_review", "srs_changes_requested",
          "srs_approved", "implementation", "final_evaluation", "completed"]
LABELS = {
    "allocated": "Project Allocated", "srs_preparation": "SRS Preparation", "srs_submitted": "SRS Submitted",
    "srs_under_review": "SRS Under Review", "srs_changes_requested": "SRS Changes Requested",
    "srs_approved": "SRS Approved", "implementation": "Implementation", "final_evaluation": "Final Evaluation",
    "completed": "Completed",
}
ORDER = {s: i for i, s in enumerate(STAGES)}
STUDENT_SIDE = {"student", "domain_lead", "admin"}

# from -> {to: (roles allowed, system_only)}. system_only steps are performed by other modules
# (SRS submission / review) via `transition(..., system=True)`, never by the public API.
TRANSITIONS = {
    "allocated": {"srs_preparation": (STUDENT_SIDE, False)},
    "srs_preparation": {"srs_submitted": ({"student"}, True)},
    "srs_submitted": {"srs_under_review": ({"mentor", "admin"}, True),
                      "srs_approved": ({"mentor", "admin"}, True),
                      "srs_changes_requested": ({"mentor", "admin"}, True)},
    "srs_under_review": {"srs_approved": ({"mentor", "admin"}, True),
                         "srs_changes_requested": ({"mentor", "admin"}, True)},
    "srs_changes_requested": {"srs_submitted": ({"student"}, True)},
    "srs_approved": {"implementation": (STUDENT_SIDE, False)},
    "implementation": {"final_evaluation": ({"mentor", "admin"}, False)},
    "final_evaluation": {"completed": ({"mentor", "admin"}, False)},
}
REOPEN_TARGETS = ("srs_preparation", "implementation", "final_evaluation")


def _reviews_submitted(project):
    return db.session.query(ProjectReview).filter_by(project_id=project.id, status="submitted").count()


def _guard(project, to):
    """Business preconditions beyond the transition table. Returns an error message or None."""
    if to == "final_evaluation" and _reviews_submitted(project) < 4:
        return "All four weekly reviews must be submitted before the final evaluation"
    if to == "completed":
        if _reviews_submitted(project) < 4:
            return "All four weekly reviews must be submitted before completion"
        if not project.final_signed_off_by:
            return "The mandatory final evaluation sign-off has not been completed"
    return None


def available_actions(project, role):
    """Manual transitions this role could take from the current stage, with guard feedback."""
    out = []
    for to, (roles, system_only) in TRANSITIONS.get(project.stage, {}).items():
        if system_only or role not in roles:
            continue
        reason = _guard(project, to)
        out.append({"to": to, "label": LABELS[to], "enabled": reason is None, "reason": reason})
    return out


def log_activity(project_id, actor_id, action, details=None):
    db.session.add(ProjectActivityLog(project_id=project_id, actor_id=actor_id, action=action,
                                      details=details, created_at=utcnow()))


def record_initial(project, actor_id):
    db.session.add(ProjectLifecycleTransition(project_id=project.id, from_stage=None, to_stage="allocated",
                                              actor_id=actor_id, created_at=utcnow()))
    log_activity(project.id, actor_id, "project.allocated", {"problem_statement_id": project.problem_statement_id})


def transition(project, to, actor, reason=None, system=False):
    """Move a project to `to`, enforcing the transition table, roles and guards."""
    allowed = TRANSITIONS.get(project.stage, {})
    if to not in allowed:
        raise AppError(f"A project in '{LABELS[project.stage]}' cannot move to '{LABELS.get(to, to)}'", 409)
    roles, system_only = allowed[to]
    if system_only and not system:
        raise AppError("This step happens automatically through the SRS workflow", 409)
    if actor.role_name not in roles:
        raise Forbidden("Your role cannot perform this transition")
    msg = _guard(project, to)
    if msg:
        raise AppError(msg, 409)

    old, now = project.stage, utcnow()
    project.stage = to
    if to == "implementation":
        project.implementation_started_at = now
    if to == "completed":
        project.completed_at = now
    db.session.add(ProjectLifecycleTransition(project_id=project.id, from_stage=old, to_stage=to,
                                              actor_id=actor.id, reason=reason, created_at=now))
    log_activity(project.id, actor.id, "stage.changed", {"from": old, "to": to, "reason": reason})
    if to == "completed":
        from app.services.project_service import member_user_ids
        notify(member_user_ids(project) | domain_lead_user_ids(project.batch.domain_id), "project_completed",
               "Project completed", f"“{project.title}” has been marked as completed.", f"/projects/{project.id}")
    return project


def close(project, actor):
    """The domain lead (or an admin) closes a completed project. Closing is undone by reopening."""
    if actor.role_name not in ("domain_lead", "admin"):
        raise Forbidden("Only the domain lead can close a project")
    if project.stage != "completed":
        raise AppError("Only a completed project can be closed", 409)
    if project.closed_at:
        raise AppError("This project is already closed", 409)
    project.closed_at, project.closed_by = utcnow(), actor.id
    log_activity(project.id, actor.id, "project.closed")
    audit(actor.id, "project.close", "project", project.id)
    from app.services.project_service import member_user_ids, mentor_user_ids
    notify(member_user_ids(project) | mentor_user_ids(project), "project_closed", "Project closed",
           f"\u201c{project.title}\u201d has been closed by the domain lead.", f"/projects/{project.id}")
    return project


def reopen(project, to, actor, reason):
    """Controlled rollback by the domain lead (own domain, enforced by project scope) or an admin.
    Needs a reason and leaves an audit record."""
    if actor.role_name not in ("admin", "domain_lead"):
        raise Forbidden("Only the domain lead or an administrator can reopen a project")
    if to not in REOPEN_TARGETS:
        raise AppError(f"A project can be reopened to: {', '.join(REOPEN_TARGETS)}", 422)
    if not reason or len(reason.strip()) < 5:
        raise AppError("A reason (at least 5 characters) is required to reopen a project", 422)
    if ORDER[to] >= ORDER[project.stage]:
        raise AppError("A project can only be reopened to an earlier stage", 409)

    old, now = project.stage, utcnow()
    project.stage = to
    project.completed_at = None
    project.closed_at = project.closed_by = None
    if ORDER[to] < ORDER["final_evaluation"]:
        project.final_signed_off_by = None
    if ORDER[to] < ORDER["implementation"]:
        project.implementation_started_at = None
    db.session.add(ProjectLifecycleTransition(project_id=project.id, from_stage=old, to_stage=to,
                                              actor_id=actor.id, reason=reason.strip(), is_reopen=True, created_at=now))
    log_activity(project.id, actor.id, "project.reopened", {"from": old, "to": to, "reason": reason.strip()})
    audit(actor.id, "project.reopen", "project", project.id, {"from": old, "to": to, "reason": reason.strip()})

    from app.services.project_service import member_user_ids, mentor_user_ids
    notify(member_user_ids(project) | mentor_user_ids(project) | domain_lead_user_ids(project.batch.domain_id),
           "project_reopened", "Project reopened",
           f"“{project.title}” was reopened to {LABELS[to]}. Reason: {reason.strip()}", f"/projects/{project.id}")
    return project
