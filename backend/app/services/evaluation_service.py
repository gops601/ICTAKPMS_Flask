"""Weekly reviews: dynamic criteria, scoring, submission, audited re-opening and final sign-off.

Nothing about criteria is hardcoded: mentors define them per review (optionally from their own templates).
A submitted review is immutable until a mentor/admin re-opens it with a reason; the superseded state is
snapshotted in `evaluation_revisions` so the evaluation history is complete.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.extensions import db
from app.models import (EvaluationCriterion, EvaluationRevision, EvaluationScore, EvaluationTemplate, Mentor, Project,
                        ProjectReview, ReviewStudentRemark)
from app.models.base import utcnow
from app.permissions.scope import mentor_profile
from app.services import lifecycle
from app.services.fields import parse_date
from app.services.notification_service import domain_lead_user_ids, notify
from app.services.project_service import PROJECT_WEEKS, member_user_ids, mentor_user_ids
from app.utils.audit import audit
from app.utils.errors import AppError, Forbidden, NotFound

CENT = Decimal("0.01")
MAX_CRITERIA = 20
MAX_MARKS = Decimal("1000")
EDITABLE = ("pending", "draft", "reopened")
FEEDBACK_FIELDS = ("remarks", "strengths", "improvements", "recommendations")
STATUS_LABEL = {"pending": "Pending", "draft": "In progress", "reopened": "Under revision", "submitted": "Submitted"}

# Example criteria offered by "Add sample templates". Purely illustrative data the mentor can edit or delete;
# no code path depends on these names.
SAMPLE_TEMPLATES = {
    1: ("Week 1 – SRS & Analysis (sample)", [("Problem Understanding", 20), ("Requirement Analysis", 20), ("SRS Quality", 30), ("Technical Feasibility", 30)]),
    2: ("Week 2 – Design & Progress (sample)", [("System Design", 20), ("Database Design", 20), ("Implementation Progress", 30), ("Code Quality", 30)]),
    3: ("Week 3 – Build & Test (sample)", [("Functional Implementation", 30), ("Code Quality", 20), ("Testing", 20), ("Scrum Progress", 30)]),
    4: ("Week 4 – Final (sample)", [("Final Implementation", 30), ("Testing and Validation", 20), ("Documentation", 20), ("Presentation and Demonstration", 30)]),
}


# ------------------------------------------------------------- numbers
def to_decimal(value, label):
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise AppError(f"{label} must be a number", 422)
    if not d.is_finite():
        raise AppError(f"{label} must be a number", 422)
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _f(d):
    return float(d) if d is not None else None


def summarize(review):
    """Totals for one review. Percentage is based on max marks of ALL criteria (unscored ones count as 0)."""
    total_max = sum((c.max_marks for c in review.criteria), Decimal("0"))
    scored = [c for c in review.criteria if c.score is not None]
    obtained = sum((c.score.marks_obtained for c in scored), Decimal("0"))
    pct = (obtained * 100 / total_max).quantize(CENT, rounding=ROUND_HALF_UP) if total_max else Decimal("0.00")
    return {"total_obtained": _f(obtained), "total_max": _f(total_max), "percentage": _f(pct),
            "criteria_count": len(review.criteria), "scored_count": len(scored)}


def overall_performance(project_id):
    """Project-level performance across SUBMITTED reviews only."""
    reviews = (db.session.query(ProjectReview).filter_by(project_id=project_id, status="submitted")
               .order_by(ProjectReview.week_no).all())
    rows = [{"week_no": r.week_no, **summarize(r)} for r in reviews]
    total_max = sum(Decimal(str(x["total_max"])) for x in rows)
    obtained = sum(Decimal(str(x["total_obtained"])) for x in rows)
    return {
        "reviews_submitted": len(rows), "reviews_total": PROJECT_WEEKS, "reviews": rows,
        "total_obtained": _f(obtained), "total_max": _f(total_max),
        "percentage": _f((obtained * 100 / total_max).quantize(CENT, rounding=ROUND_HALF_UP)) if total_max else 0.0,
        "average_percentage": round(sum(x["percentage"] for x in rows) / len(rows), 2) if rows else 0.0,
    }


# ------------------------------------------------------------ permissions
def week_gate(project, week_no):
    """Why this week cannot be evaluated yet (None when it can)."""
    order = lifecycle.ORDER[project.stage]
    if project.stage == "completed":
        return "This project is completed. Reopen it before changing evaluations."
    if week_no == 1 and project.stage == "allocated":
        return "The student has not started SRS preparation yet."
    if week_no > 1 and order < lifecycle.ORDER["implementation"]:
        return "Weeks 2–4 can be evaluated once implementation has started (SRS approved)."
    return None


def is_assigned_mentor(user, project):
    from app.services.project_service import mentors_for_project
    m = mentor_profile(user)
    return bool(m and any(x.id == m.id for x in mentors_for_project(project)))


def review_permissions(user, review):
    project = db.session.get(Project, review.project_id)
    gate = week_gate(project, review.week_no)
    assigned = user.role_name == "mentor" and is_assigned_mentor(user, project)
    can_edit = assigned and review.status in EDITABLE and gate is None
    # Only mentors score. Mentors/admins can reopen for corrections and a Domain Lead (project already scoped by the
    # route) can revert a submitted score to the mentor for further updating.
    can_reopen = (assigned or user.role_name in ("admin", "domain_lead")) and review.status == "submitted" and project.stage != "completed"
    return {"can_edit": can_edit, "can_submit": can_edit, "can_reopen": can_reopen,
            "reason": None if can_edit else (gate or ("Submitted reviews are read-only. Reopen to correct them." if review.status == "submitted" else None))}


# --------------------------------------------------------- serialisation
def criterion_to_dict(c):
    return {"id": c.id, "name": c.name, "max_marks": _f(c.max_marks), "display_order": c.display_order,
            "marks_obtained": _f(c.score.marks_obtained) if c.score else None, "remarks": c.score.remarks if c.score else None}


def student_remark_rows(review, only_student_id=None):
    """One row per project member (empty remark if none yet); a student only ever gets their own row."""
    project = db.session.get(Project, review.project_id)
    existing = {r.student_id: r.remarks for r in review.student_remarks}
    rows = [{"student_id": m.student_id, "name": m.student.user.name, "registration_no": m.student.registration_no,
             "remarks": existing.get(m.student_id, "")} for m in project.members]
    return [r for r in rows if only_student_id is None or r["student_id"] == only_student_id]


def revert_note(review):
    """Why/who sent a review back (shown to the mentor while it is under revision)."""
    if review.status != "reopened":
        return None
    from app.models import User
    rev = db.session.query(EvaluationRevision).filter_by(review_id=review.id).order_by(EvaluationRevision.id.desc()).first()
    if not rev:
        return None
    u = db.session.get(User, rev.changed_by) if rev.changed_by else None
    return {"reason": rev.reason, "by": u.name if u else "Unknown", "by_role": u.role_name if u else None, "at": rev.created_at.isoformat()}


def review_to_dict(review, role, viewer_student_id=None):
    """Full view for evaluators/monitors; students only ever receive submitted evaluations (and only their own remark)."""
    base = {"id": review.id, "project_id": review.project_id, "week_no": review.week_no,
            "due_date": review.due_date.isoformat() if review.due_date else None,
            "is_overdue": bool(review.due_date and review.status != "submitted" and review.due_date < date.today()),
            "status": review.status, "status_label": STATUS_LABEL[review.status], "version": review.version}
    if role == "student" and review.status != "submitted":
        return {**base, "visible": False, "status": "pending", "status_label": "Pending" if review.status != "reopened" else "Under revision",
                "review_date": review.review_date.isoformat() if review.review_date else None}
    m = db.session.get(Mentor, review.mentor_id) if review.mentor_id else None
    mentor = m.user.name if m else None
    return {**base, "visible": True, "review_date": review.review_date.isoformat() if review.review_date else None,
            "mentor": mentor, "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            **{f: getattr(review, f) for f in FEEDBACK_FIELDS},
            "criteria": [criterion_to_dict(c) for c in review.criteria], "summary": summarize(review),
            "student_remarks": student_remark_rows(review, viewer_student_id if role == "student" else None),
            "revert_note": None if role == "student" else revert_note(review)}


# --------------------------------------------------------------- lookups
def get_review_or_404(review_id):
    r = db.session.get(ProjectReview, review_id)
    if not r:
        raise NotFound("Review not found")
    return r


def _lock(project_id):
    return db.session.query(Project).filter_by(id=project_id).with_for_update().one()


# ------------------------------------------------------------ validation
def _clean_criteria(items):
    if not isinstance(items, list):
        raise AppError("criteria must be a list", 422)
    if len(items) > MAX_CRITERIA:
        raise AppError(f"At most {MAX_CRITERIA} criteria per review", 422)
    out, seen, errors = [], set(), {}
    for i, it in enumerate(items):
        name = (it.get("name") or "").strip()
        key = f"criteria.{i}"
        if not name:
            errors[f"{key}.name"] = "Criterion name is required"
        elif len(name) > 150:
            errors[f"{key}.name"] = "Criterion name is too long (max 150)"
        elif name.lower() in seen:
            errors[f"{key}.name"] = f"Duplicate criterion '{name}'"
        seen.add(name.lower())
        try:
            mx = to_decimal(it.get("max_marks"), "Maximum marks")
            if mx <= 0 or mx > MAX_MARKS:
                errors[f"{key}.max_marks"] = f"Maximum marks must be between 0.01 and {MAX_MARKS}"
        except AppError as e:
            errors[f"{key}.max_marks"], mx = e.message, None
        marks = None
        if it.get("marks_obtained") not in (None, ""):
            try:
                marks = to_decimal(it["marks_obtained"], "Marks")
                if marks < 0:
                    errors[f"{key}.marks_obtained"] = "Marks cannot be negative"
                elif mx is not None and marks > mx:
                    errors[f"{key}.marks_obtained"] = f"Marks cannot exceed the maximum ({mx})"
            except AppError as e:
                errors[f"{key}.marks_obtained"] = e.message
        remarks = (it.get("remarks") or "").strip()[:2000] or None
        out.append({"id": it.get("id"), "name": name, "max_marks": mx, "marks": marks, "remarks": remarks})
    if errors:
        raise AppError("Validation failed", 422, errors)
    return out


def _apply_criteria(review, cleaned):
    existing = {c.id: c for c in review.criteria}
    keep = set()
    for order, item in enumerate(cleaned):
        crit = None
        if item["id"] is not None:
            crit = existing.get(item["id"])
            if crit is None:
                raise AppError("A criterion does not belong to this review", 422)
        if crit is None:
            crit = EvaluationCriterion(review_id=review.id, name=item["name"], max_marks=item["max_marks"], display_order=order)
            db.session.add(crit)
            db.session.flush()
        else:
            crit.name, crit.max_marks, crit.display_order = item["name"], item["max_marks"], order
        keep.add(crit.id)
        if item["marks"] is None:
            if crit.score is not None:
                db.session.delete(crit.score)
                crit.score = None
        elif crit.score is None:
            crit.score = EvaluationScore(criterion_id=crit.id, marks_obtained=item["marks"], remarks=item["remarks"])
        else:
            crit.score.marks_obtained, crit.score.remarks = item["marks"], item["remarks"]
    for cid, crit in existing.items():
        if cid not in keep:
            db.session.delete(crit)
    db.session.flush()
    db.session.expire(review, ["criteria"])


def _apply_feedback(review, payload):
    for f in FEEDBACK_FIELDS:
        if f in payload:
            text = (payload[f] or "").strip()
            if len(text) > 5000:
                raise AppError(f"{f.capitalize()} is too long (max 5000 characters)", 422, {f: "Too long"})
            setattr(review, f, text or None)
    if "review_date" in payload:
        try:
            new_date = parse_date(payload["review_date"]) if payload["review_date"] else None
        except ValueError as e:
            raise AppError(str(e), 422, {"review_date": str(e)})
        if review.review_date is not None and new_date != review.review_date:
            # Scheduled dates move only through an approved request (services/review_schedule_service.py).
            raise AppError("The review date is already scheduled. Request a change – your Domain Lead must approve it.", 422,
                           {"review_date": "Already scheduled; request a change for approval"})
        review.review_date = new_date


def _apply_student_remarks(review, project, items, user):
    """items: [{student_id, remarks}]. Only members of this project; empty text removes the remark."""
    if items is None:
        return
    members = {m.student_id for m in project.members}
    existing = {r.student_id: r for r in review.student_remarks}
    errors = {}
    for i, it in enumerate(items):
        sid = it.get("student_id")
        if sid not in members:
            errors[f"student_remarks.{i}"] = "Not a member of this project"
            continue
        text = (it.get("remarks") or "").strip()
        if len(text) > 2000:
            errors[f"student_remarks.{i}"] = "Remarks are too long (max 2000 characters)"
            continue
        row = existing.get(sid)
        if not text:
            if row:
                db.session.delete(row)
        elif row:
            row.remarks, row.updated_by = text, user.id
        else:
            db.session.add(ReviewStudentRemark(review_id=review.id, student_id=sid, remarks=text, updated_by=user.id))
    if errors:
        raise AppError("Validation failed", 422, errors)
    db.session.flush()
    db.session.expire(review, ["student_remarks"])


def _prepare(review, user):
    """Common preconditions for writing to a review; returns the locked, refreshed review + project."""
    project = _lock(review.project_id)
    db.session.refresh(review, with_for_update=True)
    if user.role_name != "mentor":
        raise Forbidden("Only the project's mentor can evaluate")
    if not is_assigned_mentor(user, project):
        raise NotFound("Review not found")
    gate = week_gate(project, review.week_no)
    if gate:
        raise AppError(gate, 409)
    if review.status not in EDITABLE:
        raise AppError("This review was already submitted. Reopen it (with a reason) to make changes.", 409)
    return project


# ------------------------------------------------------------- operations
def save_draft(review, payload, user):
    project = _prepare(review, user)
    expected = payload.get("version")
    if expected is not None and expected != review.version:
        raise AppError("This evaluation was changed elsewhere. Reload and try again.", 409)
    if "criteria" in payload:
        _apply_criteria(review, _clean_criteria(payload["criteria"]))
    _apply_feedback(review, payload)
    _apply_student_remarks(review, project, payload.get("student_remarks"), user)
    review.mentor_id = mentor_profile(user).id
    if review.status == "pending":
        review.status = "draft"
    review.version += 1
    lifecycle.log_activity(project.id, user.id, "review.saved", {"week": review.week_no})
    return review


def submit(review, payload, user):
    project = _prepare(review, user)
    if payload.get("version") is not None and payload["version"] != review.version:
        raise AppError("This evaluation was changed elsewhere. Reload and try again.", 409)
    if "criteria" in payload:
        _apply_criteria(review, _clean_criteria(payload["criteria"]))
    _apply_feedback(review, payload)
    _apply_student_remarks(review, project, payload.get("student_remarks"), user)
    db.session.flush()
    errors = {}
    if not review.criteria:
        errors["criteria"] = "Add at least one evaluation criterion"
    missing = [c.name for c in review.criteria if c.score is None]
    if missing:
        errors["criteria"] = "Score every criterion before submitting: " + ", ".join(missing)
    if not (review.remarks or "").strip():
        errors["remarks"] = "Overall feedback is required to submit"
    if errors:
        raise AppError(next(iter(errors.values())), 422, errors)
    review.mentor_id = mentor_profile(user).id
    review.status, review.submitted_at = "submitted", utcnow()
    review.review_date = review.review_date or date.today()
    review.version += 1
    s = summarize(review)
    lifecycle.log_activity(project.id, user.id, "review.submitted", {"week": review.week_no, "percentage": s["percentage"]})
    audit(user.id, "review.submit", "project_review", review.id, {"project_id": project.id, "week": review.week_no})
    db.session.flush()
    notify(member_user_ids(project), "review_completed", f"Week {review.week_no} review completed",
           f"Your Week {review.week_no} evaluation is ready: {s['total_obtained']:g}/{s['total_max']:g} ({s['percentage']:g}%).",
           "/student/reviews")
    return review


def reopen(review, reason, user):
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AppError("A reason (at least 5 characters) is required to reopen a review", 422, {"reason": "Reason required"})
    project = _lock(review.project_id)
    db.session.refresh(review, with_for_update=True)
    if user.role_name == "mentor":
        if not is_assigned_mentor(user, project):
            raise NotFound("Review not found")
    elif user.role_name not in ("admin", "domain_lead"):    # domain-lead scope was already enforced by the route
        raise Forbidden("Only the project's mentor, its Domain Lead or an administrator can reopen a review")
    if review.status != "submitted":
        raise AppError("Only submitted reviews can be reopened", 409)
    if project.stage == "completed":
        raise AppError("The project is completed. Reopen the project first.", 409)
    snapshot = review_to_dict(review, "admin")
    db.session.add(EvaluationRevision(review_id=review.id, snapshot=snapshot, reason=reason, changed_by=user.id, created_at=utcnow()))
    review.status, review.submitted_at = "reopened", None
    review.version += 1
    lifecycle.log_activity(project.id, user.id, "review.reopened", {"week": review.week_no, "reason": reason})
    audit(user.id, "review.reopen", "project_review", review.id, {"project_id": project.id, "week": review.week_no, "reason": reason})
    db.session.flush()
    notify(member_user_ids(project), "review_reopened", f"Week {review.week_no} review under revision",
           "This evaluation was reopened for correction. You'll be notified when it is resubmitted.", "/student/reviews")
    if user.role_name != "mentor":   # tell the mentor(s) their score was sent back, with the reason
        who = "Your Domain Lead" if user.role_name == "domain_lead" else "An administrator"
        notify(mentor_user_ids(project), "review_reverted", f"Week {review.week_no} score reverted for update",
               f"{who} ({user.name}) reverted “{project.title}” Week {review.week_no} to you. Reason: {reason}", f"/reviews/{review.id}")
    return review


def revisions(review):
    from app.models import User
    out = []
    for rev in sorted(review.revisions, key=lambda r: r.id, reverse=True):
        u = db.session.get(User, rev.changed_by) if rev.changed_by else None
        out.append({"id": rev.id, "reason": rev.reason, "changed_by": u.name if u else "Unknown",
                    "at": rev.created_at.isoformat(), "snapshot": rev.snapshot})
    return out


def final_signoff(project, remarks, user):
    remarks = (remarks or "").strip()
    if len(remarks) < 3:
        raise AppError("Final evaluation remarks are required", 422, {"remarks": "Remarks required"})
    project = _lock(project.id)
    if user.role_name == "mentor":
        if not is_assigned_mentor(user, project):
            raise NotFound("Project not found")
    elif user.role_name != "admin":
        raise Forbidden("Only the project's mentor or an administrator can sign off the final evaluation")
    if project.stage != "final_evaluation":
        raise AppError("The final evaluation can only be signed off while the project is in the Final Evaluation stage", 409)
    if project.final_signed_off_by:
        raise AppError("The final evaluation was already signed off", 409)
    submitted = db.session.query(ProjectReview).filter_by(project_id=project.id, status="submitted").count()
    if submitted < PROJECT_WEEKS:
        raise AppError("All four weekly reviews must be submitted first", 409)
    project.final_signed_off_by, project.final_remarks = user.id, remarks
    lifecycle.log_activity(project.id, user.id, "final.signed_off", {})
    audit(user.id, "project.final_signoff", "project", project.id)
    notify(member_user_ids(project) | domain_lead_user_ids(project.batch.domain_id), "final_signed_off", "Final evaluation completed",
           f"The final evaluation of “{project.title}” was signed off.", f"/projects/{project.id}")
    return project


# --------------------------------------------------------------- templates
def clean_template_criteria(items):
    cleaned = _clean_criteria([{"name": i.get("name"), "max_marks": i.get("max_marks")} for i in items])
    return [{"name": c["name"], "max_marks": float(c["max_marks"])} for c in cleaned]


def apply_template(review, template, user):
    _prepare(review, user)
    if template.owner_id != user.id:
        raise NotFound("Template not found")
    _apply_criteria(review, [{"id": None, "name": c["name"], "max_marks": Decimal(str(c["max_marks"])), "marks": None, "remarks": None}
                             for c in template.criteria])
    if review.status == "pending":
        review.status = "draft"
    review.mentor_id = mentor_profile(user).id
    review.version += 1
    return review


def create_samples(user):
    created = []
    existing = {t.name for t in db.session.query(EvaluationTemplate).filter_by(owner_id=user.id)}
    for week, (name, crit) in SAMPLE_TEMPLATES.items():
        if name in existing:
            continue
        t = EvaluationTemplate(owner_id=user.id, name=name, week_no=week,
                               criteria=[{"name": n, "max_marks": m} for n, m in crit])
        db.session.add(t)
        created.append(t)
    db.session.flush()
    return created
