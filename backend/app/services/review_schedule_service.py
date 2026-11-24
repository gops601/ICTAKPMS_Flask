"""Review-date change requests.

The mentor may assign a review date freely the first time. Once a date is scheduled it is locked: moving it
needs a request that the project's Domain Lead (or an administrator, as a fallback when a domain has no lead)
approves. Nothing else about scoring is affected.
"""
from datetime import date

from app.extensions import db
from app.models import Project, ProjectReview, ReviewDateRequest, User
from app.models.base import utcnow
from app.services import evaluation_service as ev
from app.services import lifecycle
from app.services.fields import parse_date
from app.services.notification_service import domain_lead_user_ids, notify
from app.services.project_service import member_user_ids
from app.utils.audit import audit
from app.utils.errors import AppError, Forbidden, NotFound

MIN_REASON = 5


def pending_request(review_id):
    return (db.session.query(ReviewDateRequest).filter_by(review_id=review_id, status="pending")
            .order_by(ReviewDateRequest.id.desc()).first())


def _name(uid):
    u = db.session.get(User, uid) if uid else None
    return u.name if u else None


def request_to_dict(req):
    review = db.session.get(ProjectReview, req.review_id)
    project = db.session.get(Project, review.project_id)
    return {
        "id": req.id, "review_id": review.id, "week_no": review.week_no, "status": req.status,
        "old_date": req.old_date.isoformat(), "new_date": req.new_date.isoformat(),
        "due_date": review.due_date.isoformat() if review.due_date else None, "reason": req.reason,
        "requested_by": _name(req.requested_by), "requested_at": req.created_at.isoformat(),
        "decided_by": _name(req.decided_by), "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "decision_note": req.decision_note,
        "project": {"id": project.id, "title": project.title, "batch": {"id": project.batch.id, "code": project.batch.code},
                    "students": [m.student.user.name for m in project.members]},
    }


def lock_check(review, new_value):
    """Used when a mentor saves a review: a scheduled date cannot be edited in place."""
    if review.review_date is not None and new_value != review.review_date:
        raise AppError("The review date is already scheduled. Request a change – your Domain Lead must approve it.", 422,
                       {"review_date": "Already scheduled; request a change for approval"})


def request_change(review, new_date_raw, reason, user):
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise AppError(f"A reason (at least {MIN_REASON} characters) is required", 422, {"reason": "Reason required"})
    try:
        new_date = parse_date(new_date_raw)
    except (ValueError, TypeError) as e:
        raise AppError(str(e), 422, {"new_date": str(e)})
    project = db.session.query(Project).filter_by(id=review.project_id).with_for_update().one()
    db.session.refresh(review, with_for_update=True)
    if not ev.is_assigned_mentor(user, project):
        raise Forbidden("Only the project's mentor can request a review-date change")
    if review.status not in ev.EDITABLE:
        raise AppError("A submitted review's date cannot be changed", 409)
    if review.review_date is None:
        raise AppError("No review date has been scheduled yet – just set it, no approval is needed", 409)
    if new_date < date.today():
        raise AppError("The new review date cannot be in the past", 422, {"new_date": "Cannot be in the past"})
    if new_date == review.review_date:
        raise AppError("That is already the scheduled review date", 422, {"new_date": "Same as the current date"})
    if pending_request(review.id):
        raise AppError("A date-change request for this review is already awaiting approval", 409)
    req = ReviewDateRequest(review_id=review.id, requested_by=user.id, old_date=review.review_date, new_date=new_date, reason=reason)
    db.session.add(req)
    db.session.flush()
    lifecycle.log_activity(project.id, user.id, "review.date_requested", {"week": review.week_no, "from": req.old_date.isoformat(), "to": new_date.isoformat()})
    audit(user.id, "review.date_request", "project_review", review.id, {"from": req.old_date.isoformat(), "to": new_date.isoformat(), "reason": reason})
    notify(domain_lead_user_ids(project.batch.domain_id), "review_date_requested", "Review date change needs your approval",
           f"{user.name} asked to move Week {review.week_no} of “{project.title}” from {req.old_date} to {new_date}. Reason: {reason}",
           "/lead/date-requests")
    return req


def decide(req, decision, note, user):
    if decision not in ("approve", "reject"):
        raise AppError("decision must be approve or reject", 422)
    if user.role_name not in ("domain_lead", "admin"):          # lead scope is enforced by the route
        raise Forbidden("Only the Domain Lead can approve or reject date changes")
    note = (note or "").strip()
    if decision == "reject" and len(note) < 3:
        raise AppError("Please give a reason when rejecting a date change", 422, {"note": "Reason required"})
    review = db.session.get(ProjectReview, req.review_id)
    project = db.session.query(Project).filter_by(id=review.project_id).with_for_update().one()
    db.session.refresh(req, with_for_update=True)
    db.session.refresh(review, with_for_update=True)
    if req.status != "pending":
        raise AppError(f"This request was already {req.status}", 409)
    if decision == "approve" and review.status not in ev.EDITABLE:
        raise AppError("The review has already been submitted, so its date can no longer be changed", 409)
    req.status = "approved" if decision == "approve" else "rejected"
    req.decided_by, req.decided_at, req.decision_note = user.id, utcnow(), note or None
    mentor_ids = {req.requested_by} if req.requested_by else set()
    if decision == "approve":
        review.review_date = req.new_date
        review.version += 1
        notify(member_user_ids(project), "review_rescheduled", f"Week {review.week_no} review rescheduled",
               f"Your Week {review.week_no} review for “{project.title}” was moved from {req.old_date}; it is now scheduled for {req.new_date}.", "/student/reviews")
        notify(mentor_ids, "review_date_approved", "Review date change approved",
               f"{user.name} approved moving Week {review.week_no} of “{project.title}” to {req.new_date}.", f"/reviews/{review.id}")
    else:
        notify(mentor_ids, "review_date_rejected", "Review date change rejected",
               f"{user.name} rejected moving Week {review.week_no} of “{project.title}” to {req.new_date}. Reason: {note}", f"/reviews/{review.id}")
    lifecycle.log_activity(project.id, user.id, f"review.date_{req.status}", {"week": review.week_no, "to": req.new_date.isoformat()})
    audit(user.id, f"review.date_{req.status}", "project_review", review.id, {"request_id": req.id, "to": req.new_date.isoformat(), "note": note})
    return req


def cancel(req, user):
    review = db.session.get(ProjectReview, req.review_id)
    project = db.session.get(Project, review.project_id)
    if not ev.is_assigned_mentor(user, project):
        raise Forbidden("Only the project's mentor can withdraw a request")
    db.session.refresh(req, with_for_update=True)
    if req.status != "pending":
        raise AppError(f"This request was already {req.status}", 409)
    req.status, req.decided_by, req.decided_at = "cancelled", user.id, utcnow()
    audit(user.id, "review.date_cancelled", "project_review", review.id, {"request_id": req.id})
    return req
