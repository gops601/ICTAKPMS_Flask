import hashlib
import logging
import secrets
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models import PasswordResetToken, Role, User
from app.models.base import utcnow
from app.utils.audit import audit
from app.utils.errors import AppError

log = logging.getLogger(__name__)
MIN_PASSWORD_LEN = 8


def validate_password_strength(pw):
    if len(pw) < MIN_PASSWORD_LEN:
        raise AppError(f"Password must be at least {MIN_PASSWORD_LEN} characters", 422)
    if pw.isalpha() or pw.isdigit():
        raise AppError("Password must contain both letters and numbers", 422)


def authenticate(email, password):
    user = db.session.query(User).filter(db.func.lower(User.email) == email.strip().lower()).first()
    generic = AppError("Invalid email or password", 401)
    if not user:
        raise generic
    if user.is_locked:
        raise AppError("Account temporarily locked due to repeated failed logins. Try again later.", 423)
    if not user.check_password(password):
        user.failed_login_count += 1
        if user.failed_login_count >= current_app.config["MAX_FAILED_LOGINS"]:
            user.locked_until = utcnow() + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
            user.failed_login_count = 0
            audit(user.id, "auth.account_locked", "user", user.id)
        db.session.commit()
        raise generic
    if not user.is_active:
        raise AppError("This account has been deactivated. Contact the administrator.", 403)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit(user.id, "auth.login", "user", user.id)
    db.session.commit()
    return user


def change_password(user, current, new):
    if not user.check_password(current):
        raise AppError("Current password is incorrect", 400)
    if current == new:
        raise AppError("New password must differ from the current password", 422)
    validate_password_strength(new)
    user.set_password(new)
    user.must_change_password = False
    audit(user.id, "auth.password_changed", "user", user.id)
    db.session.commit()


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def request_password_reset(email):
    """Always succeeds from the caller's view so account existence is not revealed."""
    user = db.session.query(User).filter(db.func.lower(User.email) == email.strip().lower()).first()
    if not user or not user.is_active:
        return None
    raw = secrets.token_urlsafe(32)
    db.session.add(PasswordResetToken(
        user_id=user.id, token_hash=_hash(raw),
        expires_at=utcnow() + timedelta(minutes=current_app.config["RESET_TOKEN_MINUTES"])))
    audit(user.id, "auth.reset_requested", "user", user.id)
    db.session.commit()
    link = f"{current_app.config['FRONTEND_URL']}/reset-password/{raw}"
    # Pluggable mailer point: in dev the link is logged. Swap for SMTP in services/mailer later.
    log.info("Password reset link for %s: %s", user.email, link)
    return raw if current_app.config.get("TESTING") else None


def reset_password(raw_token, new_password):
    rec = db.session.query(PasswordResetToken).filter_by(token_hash=_hash(raw_token)).first()
    if not rec or rec.used_at or rec.expires_at < utcnow():
        raise AppError("Reset link is invalid or has expired", 400)
    validate_password_strength(new_password)
    user = db.session.get(User, rec.user_id)
    user.set_password(new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    rec.used_at = utcnow()
    audit(user.id, "auth.password_reset", "user", user.id)
    db.session.commit()


def create_user(role_name, name, email, password, phone=None, must_change_password=True):
    role = db.session.query(Role).filter_by(name=role_name).first()
    if not role:
        raise AppError(f"Unknown role '{role_name}'", 422)
    if db.session.query(User).filter(db.func.lower(User.email) == email.strip().lower()).first():
        raise AppError("A user with this email already exists", 409)
    validate_password_strength(password)
    user = User(role_id=role.id, name=name.strip(), email=email.strip().lower(), phone=phone,
                must_change_password=must_change_password)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user
