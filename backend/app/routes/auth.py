from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required
from flask_smorest import Blueprint

from app.extensions import db, limiter
from app.models import User
from app.permissions import current_user, login_required
from app.schemas.auth import (ChangePasswordSchema, ForgotPasswordSchema, LoginSchema,
                              ResetPasswordSchema, user_to_dict)
from app.services import auth_service
from app.utils.errors import AppError
from app.utils.responses import ok

bp = Blueprint("auth", __name__, url_prefix="/api/auth", description="Authentication")


def _login_limit():
    return current_app.config["LOGIN_RATE_LIMIT"]


def _tokens(user):
    claims = {"role": user.role_name}
    return {"access_token": create_access_token(str(user.id), additional_claims=claims),
            "refresh_token": create_refresh_token(str(user.id), additional_claims=claims)}


@bp.post("/login")
@limiter.limit(_login_limit)
@bp.arguments(LoginSchema)
def login(data):
    user = auth_service.authenticate(data["email"], data["password"])
    return ok({**_tokens(user), "user": user_to_dict(user)}, "Login successful")


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        raise AppError("Account is inactive", 401)
    return ok({"access_token": create_access_token(str(user.id), additional_claims={"role": user.role_name})})


@bp.get("/me")
@bp.doc(security=[{"bearerAuth": []}])
@login_required
def me():
    return ok(user_to_dict(current_user()))


@bp.post("/change-password")
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(ChangePasswordSchema)
@login_required
def change_password(data):
    auth_service.change_password(current_user(), data["current_password"], data["new_password"])
    return ok(message="Password changed successfully")


@bp.post("/forgot-password")
@limiter.limit(_login_limit)
@bp.arguments(ForgotPasswordSchema)
def forgot_password(data):
    token = auth_service.request_password_reset(data["email"])
    payload = {"token": token} if token else None  # token exposed only under TESTING
    return ok(payload, "If the account exists, a reset link has been sent")


@bp.post("/reset-password")
@limiter.limit(_login_limit)
@bp.arguments(ResetPasswordSchema)
def reset_password(data):
    auth_service.reset_password(data["token"], data["new_password"])
    return ok(message="Password reset successful")
