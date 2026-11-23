from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Notification
from app.permissions import current_user, login_required
from app.utils.errors import NotFound
from app.utils.responses import ok

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications", description="In-app notifications")
SEC = [{"bearerAuth": []}]


def _to_dict(n):
    return {"id": n.id, "type": n.type, "title": n.title, "message": n.message, "link": n.link,
            "is_read": n.is_read, "created_at": n.created_at.isoformat()}


@bp.get("")
@bp.doc(security=SEC)
@login_required
def list_notifications():
    a = request.args
    q = db.select(Notification).where(Notification.user_id == current_user().id)
    if a.get("unread") in ("1", "true"):
        q = q.where(Notification.is_read.is_(False))
    q = q.order_by(Notification.created_at.desc(), Notification.id.desc())
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    return ok([_to_dict(n) for n in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.get("/unread-count")
@bp.doc(security=SEC)
@login_required
def unread_count():
    n = db.session.query(Notification).filter_by(user_id=current_user().id, is_read=False).count()
    return ok({"count": n})


@bp.post("/<int:notification_id>/read")
@bp.doc(security=SEC)
@login_required
def mark_read(notification_id):
    n = db.session.get(Notification, notification_id)
    if not n or n.user_id != current_user().id:  # users can only touch their own notifications
        raise NotFound("Notification not found")
    n.is_read = True
    db.session.commit()
    return ok(_to_dict(n))


@bp.post("/read-all")
@bp.doc(security=SEC)
@login_required
def mark_all_read():
    db.session.query(Notification).filter_by(user_id=current_user().id, is_read=False).update({"is_read": True})
    db.session.commit()
    return ok(message="All notifications marked as read")
