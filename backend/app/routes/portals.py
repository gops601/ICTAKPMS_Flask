import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone

import jwt
from flask import request
from flask_jwt_extended import create_access_token, create_refresh_token
from flask_smorest import Blueprint
from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db, limiter
from app.models import Batch, ExternalPortal, Role, User
from app.models.base import utcnow
from app.permissions import current_user, roles_required
from app.schemas.auth import user_to_dict
from app.services import enrollment_sync_service as sync
from app.services import user_service
from app.utils.audit import audit
from app.utils.errors import AppError, Forbidden, NotFound
from app.utils.responses import ok

bp = Blueprint("portals", __name__, url_prefix="/api", description="Connect another portal: single sign-on and batch/student enrolment")
SEC = [{"bearerAuth": []}]
SSO_MAX_LIFETIME = 600          # seconds a portal token may live


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class PortalConnectionSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    base_url = fields.String(allow_none=True, validate=validate.Length(max=255))
    enrollment_path = fields.String(allow_none=True, validate=validate.Length(max=255))
    api_token = fields.String(allow_none=True, validate=validate.Length(max=255))
    default_ou_id = fields.Integer(allow_none=True)
    is_active = fields.Boolean()


class PortalConnectionPatchSchema(PortalConnectionSchema):
    name = fields.String(validate=validate.Length(min=2, max=120))


class SsoSchema(_Base):
    portal = fields.String(required=True)
    token = fields.String(required=True)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "portal"


def portal_to_dict(p, secret=None):
    base = request.host_url.rstrip("/")
    out = {"id": p.id, "name": p.name, "slug": p.slug, "base_url": p.base_url, "enrollment_path": p.enrollment_path,
           "has_api_token": bool(p.api_token), "default_ou_id": p.default_ou_id, "is_active": p.is_active,
           "last_sync_at": p.last_sync_at.isoformat() if p.last_sync_at else None, "last_sync_summary": p.last_sync_summary,
           "batch_count": db.session.query(Batch).filter_by(external_portal_id=p.id).count(),
           "sso_endpoint": f"{base}/api/auth/sso", "push_endpoint": f"{base}/api/integrations/{p.slug}/enrollments",
           "sso_login_url": f"{base}/sso?portal={p.slug}&token=<signed-token>"}
    if secret:
        out["shared_secret"] = secret          # shown once, on create / rotate
    return out


def _get(portal_id):
    p = db.session.get(ExternalPortal, portal_id)
    if not p:
        raise NotFound("Portal not found")
    return p


def _clean(value):
    return (value.strip() or None) if isinstance(value, str) else value


# ------------------------------------------------------------------ admin management
@bp.get("/admin/portals")
@bp.doc(security=SEC)
@roles_required("admin")
def list_portals():
    return ok([portal_to_dict(p) for p in db.session.query(ExternalPortal).order_by(ExternalPortal.name)])


@bp.post("/admin/portals")
@bp.doc(security=SEC, description="Register a portal. The response includes the shared secret ONCE - give it to the other portal.")
@bp.arguments(PortalConnectionSchema)
@roles_required("admin")
def create_portal(data):
    base, slug, n = _slug(data["name"]), _slug(data["name"]), 1
    while db.session.query(ExternalPortal).filter_by(slug=slug).first():
        n += 1
        slug = f"{base}-{n}"
    secret = secrets.token_urlsafe(32)
    p = ExternalPortal(slug=slug, shared_secret=secret, **{k: _clean(v) for k, v in data.items()})
    p.enrollment_path = p.enrollment_path or "/api/enrollments"
    db.session.add(p)
    db.session.flush()
    audit(current_user().id, "portal.create", "external_portal", p.id)
    db.session.commit()
    return ok(portal_to_dict(p, secret), "Portal connected", 201)


@bp.put("/admin/portals/<int:portal_id>")
@bp.doc(security=SEC)
@bp.arguments(PortalConnectionPatchSchema)
@roles_required("admin")
def update_portal(data, portal_id):
    p = _get(portal_id)
    for k, v in data.items():
        if k == "api_token" and not v:
            continue                      # blank keeps the stored token
        setattr(p, k, _clean(v))
    audit(current_user().id, "portal.update", "external_portal", p.id)
    db.session.commit()
    return ok(portal_to_dict(p))


@bp.post("/admin/portals/<int:portal_id>/rotate-secret")
@bp.doc(security=SEC, description="Issue a new shared secret (the old one stops working immediately). Returned once.")
@roles_required("admin")
def rotate_secret(portal_id):
    p = _get(portal_id)
    secret = secrets.token_urlsafe(32)
    p.shared_secret = secret
    audit(current_user().id, "portal.rotate_secret", "external_portal", p.id)
    db.session.commit()
    return ok(portal_to_dict(p, secret), "New secret issued")


@bp.delete("/admin/portals/<int:portal_id>")
@bp.doc(security=SEC, description="Disconnect a portal. Batches/students already enrolled stay; they just lose the link.")
@roles_required("admin")
def delete_portal(portal_id):
    p = _get(portal_id)
    db.session.query(Batch).filter_by(external_portal_id=p.id).update({"external_portal_id": None})
    db.session.delete(p)
    audit(current_user().id, "portal.delete", "external_portal", portal_id)
    db.session.commit()
    return ok(message="Portal disconnected")


@bp.post("/admin/portals/<int:portal_id>/sync")
@bp.doc(security=SEC, description="Pull the portal's batches and students now.")
@roles_required("admin")
def sync_portal(portal_id):
    p = _get(portal_id)
    if not p.is_active:
        raise AppError("This portal is switched off", 409)
    summary = sync.pull(p, current_user())
    audit(current_user().id, "portal.sync", "external_portal", p.id, {k: v for k, v in summary.items() if k != "problems"})
    db.session.commit()
    return ok(portal_to_dict(p), "Sync finished")


# ------------------------------------------------------------------ push from the portal
@bp.post("/integrations/<slug>/enrollments")
@bp.doc(description="Called by the other portal. Header X-Signature: sha256=<hex HMAC-SHA256 of the raw body with the shared secret>.")
@limiter.limit("60/minute")
def push_enrollments(slug):
    p = db.session.query(ExternalPortal).filter_by(slug=slug, is_active=True).first()
    raw = request.get_data()
    given = (request.headers.get("X-Signature") or "").removeprefix("sha256=")
    expected = hmac.new((p.shared_secret if p else "x").encode(), raw, hashlib.sha256).hexdigest()
    if not p or not hmac.compare_digest(given, expected):
        raise AppError("Invalid signature", 401)
    try:
        payload = json.loads(raw)
    except ValueError:
        raise AppError("Body must be JSON", 422)
    admin = (db.session.query(User).join(Role, Role.id == User.role_id)
             .filter(Role.name == "admin", User.is_active.is_(True)).order_by(User.id).first())
    summary = sync.apply(p, payload, admin)
    audit(None, "portal.push", "external_portal", p.id, {k: v for k, v in summary.items() if k != "problems"})
    db.session.commit()
    return ok(summary, "Enrolments applied")


# ------------------------------------------------------------------ single sign-on
@bp.post("/auth/sso")
@bp.doc(description="Exchange a short-lived token signed (HS256) by a connected portal for a session. "
                    "Claims: email (required), exp (required, within 10 minutes), name, batch (the portal's batch code) and reg_no for first-time students.")
@limiter.limit("30/minute")
@bp.arguments(SsoSchema)
def sso_login(data):
    portal = db.session.query(ExternalPortal).filter_by(slug=data["portal"], is_active=True).first()
    bad = AppError("Single sign-on failed. Ask the portal to retry.", 401)
    if not portal:
        raise bad
    try:
        claims = jwt.decode(data["token"], portal.shared_secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise bad
    now = datetime.now(timezone.utc).timestamp()
    if claims["exp"] - now > SSO_MAX_LIFETIME or (claims.get("iss") and claims["iss"] != portal.slug):
        raise bad
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise bad
    user = db.session.query(User).filter(db.func.lower(User.email) == email).first()
    if user is None:                      # first visit: enrol the student into the batch the portal says they belong to
        batch = (db.session.query(Batch).filter_by(external_portal_id=portal.id, external_ref=str(claims.get("batch") or "")).first()
                 if claims.get("batch") else None)
        name = str(claims.get("name") or "").strip()
        if not batch or len(name) < 2:
            raise AppError("No account for this e-mail yet. Ask the portal to enrol you in a batch first.", 403)
        student, _pw = user_service.create_student(batch, name, email, None, claims.get("reg_no"))
        user = student.user
    if user.role_name == "admin":
        raise Forbidden("Administrators sign in with their password")
    if not user.is_active:
        raise AppError("This account has been deactivated. Contact the administrator.", 403)
    user.last_login_at = utcnow()
    audit(user.id, "auth.sso_login", "user", user.id, {"portal": portal.slug})
    db.session.commit()
    extra = {"role": user.role_name}
    return ok({"access_token": create_access_token(str(user.id), additional_claims=extra),
               "refresh_token": create_refresh_token(str(user.id), additional_claims=extra), "user": user_to_dict(user)},
              "Signed in via " + portal.name)


# ------------------------------------------------------------------ documentation + configuration file
SECRET_PLACEHOLDER = "<PASTE_SHARED_SECRET_HERE>"


def build_config(p, fmt):
    base = request.host_url.rstrip("/")
    cfg = {
        "portal": {"name": p.name, "id": p.slug},
        "ictak": {
            "base_url": base,
            "sso_login_url": f"{base}/sso?portal={p.slug}&token=<JWT>",
            "sso_api_endpoint": f"{base}/api/auth/sso",
            "enrollment_push_endpoint": f"{base}/api/integrations/{p.slug}/enrollments",
            "api_documentation": f"{base}/api/docs",
        },
        "auth": {
            "shared_secret": SECRET_PLACEHOLDER,
            "sso_token": {"algorithm": "HS256", "required_claims": ["email", "exp"], "optional_claims": ["iss", "name", "batch", "reg_no"],
                          "iss_must_equal": p.slug, "max_lifetime_seconds": sync_max_lifetime()},
            "push_signature": {"header": "X-Signature", "format": "sha256=<hex HMAC-SHA256 of the raw body, key = shared_secret>"},
        },
        "enrollment_payload_example": {"batches": [{
            "code": "EXT-101", "name": "Full Stack - January 2026", "domain": "AIML", "start_date": "2026-01-05", "end_date": "2026-06-30",
            "details": {}, "students": [{"name": "Asha K", "email": "asha@example.com", "registration_no": "R-001", "phone": "9999999999"}]}]},
        "limits": {"max_batches_per_push": sync.MAX_BATCHES, "max_students_per_push": sync.MAX_STUDENTS, "push_rate_limit": "60/minute"},
    }
    if fmt == "env":
        text = "\n".join([
            f"# Integration settings for the portal '{p.name}' - generated by ICTAK",
            f"ICTAK_URL={base}", f"ICTAK_PORTAL_ID={p.slug}", f"ICTAK_SHARED_SECRET={SECRET_PLACEHOLDER}",
            f"ICTAK_SSO_LOGIN_URL={base}/sso", f"ICTAK_SSO_API_ENDPOINT={base}/api/auth/sso",
            f"ICTAK_ENROLLMENT_PUSH_ENDPOINT={base}/api/integrations/{p.slug}/enrollments",
            "ICTAK_SSO_ALGORITHM=HS256", f"ICTAK_SSO_TOKEN_MAX_SECONDS={sync_max_lifetime()}", ""])
        return text, "text/plain; charset=utf-8", f"{p.slug}-ictak.env"
    return json.dumps(cfg, indent=2) + "\n", "application/json", f"{p.slug}-ictak-config.json"


def sync_max_lifetime():
    return SSO_MAX_LIFETIME


@bp.get("/admin/portals/<int:portal_id>/config")
@bp.doc(security=SEC, description="Downloadable configuration file for the other portal (format=json|env). The shared secret is NOT included; "
                                  "it is a placeholder to fill in with the value shown when the secret was issued.")
@roles_required("admin")
def portal_config(portal_id):
    from flask import Response
    p = _get(portal_id)
    text, mime, filename = build_config(p, "env" if request.args.get("format") == "env" else "json")
    return Response(text, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/admin/portals/integration-guide")
@bp.doc(security=SEC, description="The Portal Integration Guide (Markdown): SSO + enrolment API with examples in curl, Python, Node and PHP.")
@roles_required("admin")
def integration_guide():
    import os
    from flask import Response
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs", "SSO_INTEGRATION.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return Response(text, mimetype="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ICTAK-portal-integration-guide.md"'})
