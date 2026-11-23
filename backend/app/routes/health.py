from flask import Blueprint
from sqlalchemy import text

from app.extensions import db
from app.utils.responses import ok, fail

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return fail("Database unavailable", 503)
    return ok({"status": "healthy"})
