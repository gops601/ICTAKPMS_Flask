import logging

from werkzeug.exceptions import HTTPException

from app.extensions import db
from .responses import fail

log = logging.getLogger(__name__)


class AppError(Exception):
    """Business-rule violation that maps cleanly to an HTTP response."""

    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.message, self.status, self.errors = message, status, errors


class NotFound(AppError):
    def __init__(self, message="Resource not found"):
        super().__init__(message, 404)


class Forbidden(AppError):
    def __init__(self, message="You do not have permission to perform this action"):
        super().__init__(message, 403)


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(e):
        return fail(e.message, e.status, e.errors)

    @app.errorhandler(HTTPException)
    def handle_http(e):
        errors = None
        data = getattr(e, "data", None)  # flask-smorest attaches validation messages here
        if data and isinstance(data, dict):
            errors = data.get("errors") or data.get("messages")
            if isinstance(errors, dict) and set(errors) <= {"json", "query", "form", "files"}:
                # flask-smorest nests field errors under their location; flatten for one consistent shape
                errors = {k: v for loc in errors.values() if isinstance(loc, dict) for k, v in loc.items()}
        return fail(e.description if e.code != 422 else "Validation failed", e.code, errors)

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        db.session.rollback()
        log.exception("Unhandled exception")
        return fail("Internal server error", 500)

    from app.extensions import jwt

    @jwt.unauthorized_loader
    def _missing(reason):
        return fail("Authentication required", 401)

    @jwt.invalid_token_loader
    def _invalid(reason):
        return fail("Invalid token", 401)

    @jwt.expired_token_loader
    def _expired(header, payload):
        return fail("Token has expired", 401)
