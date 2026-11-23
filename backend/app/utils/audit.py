from flask import request

from app.extensions import db
from app.models import AuditLog


def audit(user_id, action, entity_type=None, entity_id=None, details=None):
    """Record a critical action. Caller owns the commit so it joins the surrounding transaction."""
    ip = None
    try:
        ip = request.remote_addr
    except RuntimeError:
        pass
    db.session.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type,
                            entity_id=entity_id, details=details, ip_address=ip))
