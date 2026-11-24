from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models import ProjectGithubRepository, ProjectLifecycleTransition, ProjectActivityLog, User
from app.services import lifecycle, project_service, srs_service
from app.services.metrics_service import phase_for, project_weeks


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class AllocationItemSchema(_Base):
    problem_statement_id = fields.Integer(required=True)
    student_ids = fields.List(fields.Integer(), required=True, validate=validate.Length(min=1))
    team = fields.Boolean(load_default=False)


class AllocationSchema(_Base):
    batch_id = fields.Integer(required=True)
    items = fields.List(fields.Nested(AllocationItemSchema), required=True, validate=validate.Length(min=1))
    mentor_id = fields.Integer(allow_none=True, load_default=None)
    start_date = fields.String(allow_none=True, load_default=None)


class TransitionSchema(_Base):
    to = fields.String(required=True)
    reason = fields.String(allow_none=True, validate=validate.Length(max=500))


class ReopenSchema(_Base):
    to = fields.String(required=True)
    reason = fields.String(required=True, validate=validate.Length(max=500))


class ProjectMentorSchema(_Base):
    mentor_id = fields.Integer(allow_none=True, required=True)
    reason = fields.String(allow_none=True, validate=validate.Length(max=300))


class ProjectMentorsSchema(_Base):
    mentor_ids = fields.List(fields.Integer(), required=True)
    reason = fields.String(allow_none=True, validate=validate.Length(max=300))


class ProjectSettingsSchema(_Base):
    mentor_can_edit_board = fields.Boolean(required=True)


class ReassignProblemSchema(_Base):
    problem_statement_id = fields.Integer(required=True)


class BatchMentorSchema(_Base):
    mentor_id = fields.Integer(required=True)


class ReassignMentorSchema(_Base):
    to_mentor_id = fields.Integer(required=True)


def _iso(d):
    return d.isoformat() if d else None


def _lead_mentors(project, role):
    """True when a domain lead is also one of this project's mentors (so mentor actions are offered to them)."""
    if role != "domain_lead":
        return False
    try:
        from app.permissions import current_user
        from app.services.evaluation_service import is_assigned_mentor
        return is_assigned_mentor(current_user(), project)
    except Exception:           # outside a request
        return False


def project_to_dict(p, detail=False, role=None):
    mentors = project_service.mentors_for_project(p)
    reasons = project_service.delay_reasons(p)
    out = {
        "id": p.id, "code": p.code, "title": p.title, "stage": p.stage, "stage_label": lifecycle.LABELS[p.stage],
        "mode": p.batch.mode, "total_weeks": project_weeks(p),
        "week_plan": [{"week": w, "phase": phase_for(w)} for w in range(1, project_weeks(p) + 1)],
        "batch": {"id": p.batch.id, "code": p.batch.code, "name": p.batch.name,
                  "domain": {"id": p.batch.domain.id, "name": p.batch.domain.name} if p.batch.domain else None},
        "problem_statement": {"id": p.problem_statement.id, "ps_code": p.problem_statement.ps_code,
                              "title": p.problem_statement.title, "difficulty": p.problem_statement.difficulty},
        "members": [{"student_id": m.student.id, "name": m.student.user.name, "email": m.student.user.email,
                     "registration_no": m.student.registration_no, "is_lead": m.is_lead} for m in p.members],
        "mentors": [{"id": m.id, "name": m.user.name} for m in mentors],
        "mentor_override": p.mentor_id is not None,
        "start_date": _iso(p.start_date), "target_end_date": _iso(p.target_end_date),
        "progress": project_service.compute_progress(p), "is_delayed": bool(reasons), "delay_reasons": reasons,
        "mentor_can_edit_board": p.mentor_can_edit_board,
        "completed_at": _iso(p.completed_at), "closed_at": _iso(p.closed_at), "is_closed": p.closed_at is not None,
        "srs_status": srs_service.srs_status(p),
        "implementation_unlocked": srs_service.implementation_unlocked(p),
    }
    if detail:
        gh = db.session.query(ProjectGithubRepository).filter_by(project_id=p.id).first()
        out["github_url"] = gh.url if gh else None
        out["implementation_started_at"] = _iso(p.implementation_started_at)
        out["reviews"] = [{"week_no": r.week_no, "due_date": _iso(r.due_date), "status": r.status}
                          for r in sorted(_reviews(p), key=lambda r: r.week_no)]
        out["available_actions"] = lifecycle.available_actions(p, role, also_mentor=_lead_mentors(p, role)) if role else []
    return out


def _reviews(p):
    from app.models import ProjectReview
    return db.session.query(ProjectReview).filter_by(project_id=p.id).all()


def timeline(project_id):
    """Merged lifecycle transitions + activity, newest first."""
    names = {}

    def name(uid):
        if uid not in names:
            u = db.session.get(User, uid) if uid else None
            names[uid] = u.name if u else "System"
        return names[uid]

    items = []
    for t in db.session.query(ProjectLifecycleTransition).filter_by(project_id=project_id).all():
        items.append({"kind": "transition", "_id": t.id, "at": t.created_at, "actor": name(t.actor_id), "from": t.from_stage,
                      "to": t.to_stage, "reason": t.reason, "is_reopen": t.is_reopen})
    for a in db.session.query(ProjectActivityLog).filter_by(project_id=project_id).all():
        if a.action == "stage.changed":
            continue  # already represented by the transition row
        items.append({"kind": "activity", "_id": a.id, "at": a.created_at, "actor": name(a.actor_id), "action": a.action,
                      "details": a.details})
    # MySQL DATETIME has 1-second resolution, so events in the same second tie on `at`; ids break the tie.
    items.sort(key=lambda i: (i["at"], i["kind"] == "transition", i["_id"]), reverse=True)
    for i in items:
        i["at"] = i["at"].isoformat()
        del i["_id"]
    return items
