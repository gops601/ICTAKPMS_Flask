from flask import request
from sqlalchemy.exc import IntegrityError
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Domain, Role, User
from app.permissions import current_user, roles_required
from app.schemas.auth import user_to_dict
from app.schemas.org import ActiveSchema, LeadDomainsSchema, ResetPasswordAdminSchema, StaffCreateSchema, StaffCredentialsSchema
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
                                          data["domain_id"], data["designation"], data["expertise"],
                                          data["mentor_type"], data["company"], data["industry_sector"],
                                          data["experience_years"], data["linkedin_url"], data["bio"], data["domain_ids"])
    audit(current_user().id, "user.create", "user", user.id, {"role": data["role"]})
    if data["role"] == "mentor" and data["domain_id"]:
        # the domain's leads see the new mentor straight away (their Mentors page is scoped by domain) and are told
        from app.services.notification_service import domain_lead_user_ids, notify
        notify(domain_lead_user_ids(data["domain_id"]), "mentor_added", "New mentor in your domain",
               f"{user.name} joined {db.session.get(Domain, data['domain_id']).name} as a mentor. You can assign them to your batches.",
               "/lead/mentors")
    if data["role"] == "domain_lead":
        # a domain lead is also a mentor: they join the mentor list and the active batches of the domain(s) they lead
        from app.models import Mentor
        from app.services import domain_sync_service
        domain_sync_service.auto_assign_mentor_to_batches(db.session.query(Mentor).filter_by(user_id=user.id).one(), current_user())
    if data["role"] == "mentor" and data["domain_id"]:
        # ... and the mentor is put on every active batch of that domain automatically
        from app.models import Mentor
        from app.services import domain_sync_service
        mentor = db.session.query(Mentor).filter_by(user_id=user.id).one()
        domain_sync_service.auto_assign_mentor_to_batches(mentor, current_user())
        domain_sync_service.warn_admins_if_no_lead(data["domain_id"], f"Mentor {user.name}")
    db.session.commit()
    body = user_to_dict(user)
    if generated:
        body["temporary_password"] = password  # shown once; the user must change it at first login
    return ok(body, "User created", 201)


@bp.post("/users/credentials")
@bp.doc(security=SEC, description="Issue fresh temporary passwords for mentors or domain leads who have not logged in "
                                  "yet, for sharing. Returned once; never stored in clear text.")
@bp.arguments(StaffCredentialsSchema)
@roles_required("admin")
def issue_staff_credentials(data):
    issued, skipped = user_service.issue_staff_credentials(data["role"], data["user_ids"], data["include_active"])
    audit(current_user().id, "staff.credentials_issued", "user", None, {"role": data["role"], "issued": len(issued), "skipped": len(skipped),
                                                                              "include_active": data["include_active"]})
    db.session.commit()
    return ok({"credentials": issued, "skipped": skipped, "role": data["role"]}, f"{len(issued)} credential(s) issued")


@bp.delete("/users/<int:user_id>")
@bp.doc(security=SEC, description="Permanently delete a student, mentor, domain lead or administrator. Refused (409) when "
                                  "that would orphan real work; deactivate instead.")
@roles_required("admin")
def delete_user(user_id):
    user = user_service.get_user_or_404(user_id)
    try:
        info = user_service.delete_user(user, current_user())
        audit(current_user().id, "user.delete", "user", user_id, info)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AppError("This account is still referenced by other records. Deactivate it instead.", 409)
    return ok(message=f"{info['name']} was deleted")


@bp.put("/users/<int:user_id>/domains")
@bp.doc(security=SEC, description="Set the domain(s) a domain lead leads (replaces the current list). At least one is required.")
@bp.arguments(LeadDomainsSchema)
@roles_required("admin")
def set_lead_domains(data, user_id):
    user = user_service.get_user_or_404(user_id)
    domains = user_service.set_lead_domains(user, data["domain_ids"])
    audit(current_user().id, "user.set_domains", "user", user.id, {"domain_ids": [d.id for d in domains]})
    db.session.commit()
    return ok(user_to_dict(user), "Domains updated")


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
