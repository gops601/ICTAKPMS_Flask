from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Domain, Role, User
from app.permissions import current_user, roles_required
from app.schemas.auth import user_to_dict
from app.schemas.org import ActiveSchema, ResetPasswordAdminSchema, StaffCreateSchema
from app.services import user_service
from app.utils.audit import audit
from app.utils.errors import AppError
from app.utils.responses import ok

bp = Blueprint("admin", __name__, url_prefix="/api/admin", description="Admin: user management")
SEC = [{"bearerAuth": []}]


@bp.get("/users")
@bp.doc(security=SEC)
@roles_required("admin")
def list_users():
    q = db.select(User).order_by(User.created_at.desc())
    if role := request.args.get("role"):
        q = q.join(Role).where(Role.name == role)
    if term := request.args.get("q"):
        like = f"%{term}%"
        q = q.where(db.or_(User.name.like(like), User.email.like(like)))
    if request.args.get("active") in ("1", "true"):
        q = q.where(User.is_active.is_(True))
    page = db.paginate(q, page=request.args.get("page", 1, type=int),
                       per_page=min(request.args.get("per_page", 20, type=int), 100), error_out=False)
    return ok([user_to_dict(u) for u in page.items],
              meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


@bp.post("/users")
@bp.doc(security=SEC, description="Create an admin, domain lead or mentor. Students use /api/students.")
@bp.arguments(StaffCreateSchema)
@roles_required("admin")
def create_user(data):
    if data["domain_id"] and not db.session.get(Domain, data["domain_id"]):
        raise AppError("Domain not found", 422, {"domain_id": "Domain not found"})
    generated = data["password"] is None
    password = data["password"] or user_service.generate_temp_password()
    user = user_service.create_staff_user(data["role"], data["name"], data["email"], password, data["phone"],
                                          data["domain_id"], data["designation"], data["expertise"])
    audit(current_user().id, "user.create", "user", user.id, {"role": data["role"]})
    db.session.commit()
    body = user_to_dict(user)
    if generated:
        body["temporary_password"] = password  # shown once; the user must change it at first login
    return ok(body, "User created", 201)


@bp.post("/users/<int:user_id>/reset-password")
@bp.doc(security=SEC)
@bp.arguments(ResetPasswordAdminSchema)
@roles_required("admin")
def reset_password(data, user_id):
    user = user_service.get_user_or_404(user_id)
    password = user_service.reset_user_password(user, data["new_password"])
    audit(current_user().id, "user.reset_password", "user", user.id)
    db.session.commit()
    return ok({"temporary_password": password}, "Password reset; user must change it at next login")


@bp.patch("/users/<int:user_id>/active")
@bp.doc(security=SEC)
@bp.arguments(ActiveSchema)
@roles_required("admin")
def toggle_active(data, user_id):
    user = user_service.get_user_or_404(user_id)
    if user.id == current_user().id and not data["is_active"]:
        raise AppError("You cannot deactivate your own account", 422)
    user.is_active = data["is_active"]
    audit(current_user().id, "user.activate" if user.is_active else "user.deactivate", "user", user.id)
    db.session.commit()
    return ok(user_to_dict(user))
