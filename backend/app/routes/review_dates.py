from flask import request
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields

from app.extensions import db
from app.models import Project, ProjectReview, ReviewDateRequest
from app.permissions import current_user, roles_required
from app.permissions.scope import ensure_project_access, scoped_projects
from app.services import review_schedule_service as svc
from app.utils.errors import NotFound
from app.utils.responses import ok

bp = Blueprint("review_dates", __name__, url_prefix="/api", description="Review-date change requests (mentor asks, Domain Lead approves)")
SEC = [{"bearerAuth": []}]
ROLES = ("mentor", "domain_lead", "admin")


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class DateRequestSchema(_Base):
    new_date = fields.String(required=True)
    reason = fields.String(required=True)


class DecisionSchema(_Base):
    decision = fields.String(required=True)
    note = fields.String(allow_none=True)


def _request_for(request_id):
    """Fetch a request whose project the caller may access; hide existence otherwise."""
    req = db.session.get(ReviewDateRequest, request_id)
    if not req:
        raise NotFound("Request not found")
    review = db.session.get(ProjectReview, req.review_id)
    ensure_project_access(current_user(), review.project_id)
    return req


@bp.get("/reviews/<int:review_id>/date-requests")
@bp.doc(security=SEC)
@roles_required(*ROLES)
def review_history(review_id):
    review = db.session.get(ProjectReview, review_id)
    if not review:
        raise NotFound("Review not found")
    ensure_project_access(current_user(), review.project_id)
    rows = db.session.query(ReviewDateRequest).filter_by(review_id=review_id).order_by(ReviewDateRequest.id.desc()).all()
    return ok([svc.request_to_dict(r) for r in rows])


@bp.post("/reviews/<int:review_id>/date-requests")
@bp.doc(security=SEC, description="Mentor: ask to move an already-scheduled review date. Needs Domain Lead approval.")
@bp.arguments(DateRequestSchema)
@roles_required("mentor")
def create_request(data, review_id):
    review = db.session.get(ProjectReview, review_id)
    if not review:
        raise NotFound("Review not found")
    ensure_project_access(current_user(), review.project_id)
    req = svc.request_change(review, data["new_date"], data["reason"], current_user())
    db.session.commit()
    return ok(svc.request_to_dict(req), "Request sent to your Domain Lead", 201)


@bp.get("/review-date-requests")
@bp.doc(security=SEC, description="Requests in the caller's scope. status=pending|approved|rejected|cancelled, batch_id, week.")
@roles_required(*ROLES)
def list_requests():
    a = request.args
    visible = scoped_projects(current_user()).subquery()
    q = (db.select(ReviewDateRequest).join(ProjectReview, ProjectReview.id == ReviewDateRequest.review_id)
         .join(visible, visible.c.id == ProjectReview.project_id))
    if a.get("status") in ("pending", "approved", "rejected", "cancelled"):
        q = q.where(ReviewDateRequest.status == a["status"])
    if a.get("batch_id", type=int):
        q = q.join(Project, Project.id == ProjectReview.project_id).where(Project.batch_id == a.get("batch_id", type=int))
    if a.get("week", type=int):
        q = q.where(ProjectReview.week_no == a.get("week", type=int))
    q = q.order_by(db.case((ReviewDateRequest.status == "pending", 0), else_=1), ReviewDateRequest.id.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int), per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    return ok([svc.request_to_dict(r) for r in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.post("/review-date-requests/<int:request_id>/decision")
@bp.doc(security=SEC, description="Domain Lead (or admin): approve or reject. A reason is required to reject.")
@bp.arguments(DecisionSchema)
@roles_required("domain_lead", "admin")
def decide(data, request_id):
    req = svc.decide(_request_for(request_id), data["decision"], data.get("note"), current_user())
    db.session.commit()
    return ok(svc.request_to_dict(req), "Request approved" if req.status == "approved" else "Request rejected")


@bp.post("/review-date-requests/<int:request_id>/cancel")
@bp.doc(security=SEC)
@roles_required("mentor")
def cancel(request_id):
    req = svc.cancel(_request_for(request_id), current_user())
    db.session.commit()
    return ok(svc.request_to_dict(req), "Request withdrawn")
