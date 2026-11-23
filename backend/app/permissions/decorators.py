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


def roles_required(*roles):
    """Backend role gate. Role is always re-read from the DB, never trusted from the token."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = load_current_user()
            if user.role_name not in roles:
                raise Forbidden()
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    return load_current_user()
