import io

from flask import request, send_file
from flask_smorest import Blueprint

from app.extensions import db
from app.models import OrganisationalUnit, OUCustomField
from app.permissions import current_user, roles_required
from app.schemas.org import (ActiveSchema, FieldSchema, FieldUpdateSchema, OUSchema, OUUpdateSchema,
                             field_to_dict, ou_to_dict)
from app.services import org_service
from app.services.templates import build_template
from app.utils.audit import audit
from app.utils.errors import AppError, NotFound
from app.utils.responses import ok

bp = Blueprint("ous", __name__, url_prefix="/api/ous", description="Organisational units")
SEC = [{"bearerAuth": []}]


@bp.get("")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def list_ous():
    q = db.select(OrganisationalUnit).order_by(OrganisationalUnit.name)
    if request.args.get("active") in ("1", "true"):
        q = q.where(OrganisationalUnit.is_active.is_(True))
    return ok([ou_to_dict(o) for o in db.session.scalars(q)])


@bp.post("")
@bp.doc(security=SEC)
@bp.arguments(OUSchema)
@roles_required("admin")
def create_ou(data):
    ou = org_service.create_ou(data["name"], data["code"], data["description"])
    audit(current_user().id, "ou.create", "ou", ou.id, {"code": ou.code})
    db.session.commit()
    return ok(ou_to_dict(ou, True), "OU created", 201)


@bp.get("/<int:ou_id>")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def get_ou(ou_id):
    return ok(ou_to_dict(org_service.get_ou(ou_id), True))


@bp.put("/<int:ou_id>")
@bp.doc(security=SEC)
@bp.arguments(OUUpdateSchema)
@roles_required("admin")
def update_ou(data, ou_id):
    ou = org_service.update_ou(org_service.get_ou(ou_id), data.get("name"), data.get("description"))
    audit(current_user().id, "ou.update", "ou", ou.id)
    db.session.commit()
    return ok(ou_to_dict(ou, True))


@bp.patch("/<int:ou_id>/active")
@bp.doc(security=SEC)
@bp.arguments(ActiveSchema)
@roles_required("admin")
def set_active(data, ou_id):
    ou = org_service.get_ou(ou_id)
    ou.is_active = data["is_active"]
    audit(current_user().id, "ou.activate" if ou.is_active else "ou.deactivate", "ou", ou.id)
    db.session.commit()
    return ok(ou_to_dict(ou))


@bp.get("/<int:ou_id>/fields")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def list_fields(ou_id):
    ou = org_service.get_ou(ou_id)
    scope = request.args.get("scope")
    fields = [f for f in ou.custom_fields if (not scope or f.scope == scope)]
    if request.args.get("active") in ("1", "true"):
        fields = [f for f in fields if f.is_active]
    return ok([field_to_dict(f) for f in fields])


@bp.post("/<int:ou_id>/fields")
@bp.doc(security=SEC)
@bp.arguments(FieldSchema)
@roles_required("admin")
def add_field(data, ou_id):
    field = org_service.add_field(org_service.get_ou(ou_id), data)
    audit(current_user().id, "ou.field_add", "ou", ou_id, {"field": field.field_key})
    db.session.commit()
    return ok(field_to_dict(field), "Field added", 201)


@bp.put("/fields/<int:field_id>")
@bp.doc(security=SEC)
@bp.arguments(FieldUpdateSchema)
@roles_required("admin")
def update_field(data, field_id):
    field = db.session.get(OUCustomField, field_id)
    if not field:
        raise NotFound("Field not found")
    org_service.update_field(field, data)
    audit(current_user().id, "ou.field_update", "ou", field.ou_id, {"field": field.field_key})
    db.session.commit()
    return ok(field_to_dict(field))


@bp.get("/<int:ou_id>/template")
@bp.doc(security=SEC)
@roles_required("admin")
def download_template(ou_id):
    ou = org_service.get_ou(ou_id)
    kind = request.args.get("type", "batches")
    fmt = request.args.get("format", "xlsx")
    if kind not in ("batches", "students") or fmt not in ("csv", "xlsx"):
        raise AppError("type must be batches|students and format csv|xlsx", 422)
    content, mime = build_template(kind, ou, fmt)
    return send_file(io.BytesIO(content), mimetype=mime, as_attachment=True,
                     download_name=f"{ou.code.lower()}_{kind}_template.{fmt}")
