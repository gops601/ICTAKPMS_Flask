from functools import wraps

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models import User
from app.utils.errors import AppError, Forbidden


def load_current_user():
    """Return the authenticated, active user (cached per request)."""
    # Cache on the request environ (not `g`): `g` can outlive a request when an app context is reused.
    user = request.environ.get("plms.current_user")
    if user is None:
        user = db.session.get(User, int(get_jwt_identity()))
        if not user or not user.is_active:
            raise AppError("Account is inactive or no longer exists", 401)
        request.environ["plms.current_user"] = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        load_current_user()
        return fn(*args, **kwargs)
    return wrapper


def _lead_acting_as_mentor(user, roles):
    """A domain lead is also a mentor (they have a mentor profile): mentor-only endpoints admit them. What they may do on a
    given project is still decided by the per-project checks (they must be one of the project's mentors)."""
    if user.role_name != "domain_lead" or "mentor" not in roles:
        return False
    from app.models import Mentor
    return db.session.query(Mentor.id).filter_by(user_id=user.id).first() is not None


def roles_required(*roles):
    """Backend role gate. Role is always re-read from the DB, never trusted from the token."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = load_current_user()
            if user.role_name not in roles and not _lead_acting_as_mentor(user, roles):
                raise Forbidden()
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    return load_current_user()
