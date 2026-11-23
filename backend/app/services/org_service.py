"""OU, domain and batch business rules."""
import re

from app.extensions import db
from app.models import (Subdomain, Batch, BatchOUDetail, Domain, DomainLead, OrganisationalUnit, OUCustomField,
                        Student, User)
from app.utils.ids import generate_id
from app.services.fields import FIELD_TYPES, parse_date, validate_custom_value
from app.utils.errors import AppError, NotFound


def _ci_exists(model, column, value, exclude_id=None):
    q = db.session.query(model).filter(db.func.lower(column) == value.strip().lower())
    if exclude_id:
        q = q.filter(model.id != exclude_id)
    return q.first() is not None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")[:60]


# ----------------------------------------------------------------------------- OU
def create_ou(name, code, description=None):
    if _ci_exists(OrganisationalUnit, OrganisationalUnit.name, name):
        raise AppError("An OU with this name already exists", 409)
    if _ci_exists(OrganisationalUnit, OrganisationalUnit.code, code):
        raise AppError("An OU with this code already exists", 409)
    ou = OrganisationalUnit(name=name.strip(), code=code.strip().upper(), description=description)
    db.session.add(ou)
    db.session.flush()
    return ou


def update_ou(ou, name=None, description=None):
    if name and name.strip().lower() != ou.name.lower():
        if _ci_exists(OrganisationalUnit, OrganisationalUnit.name, name, ou.id):
            raise AppError("An OU with this name already exists", 409)
        ou.name = name.strip()
    if description is not None:
        ou.description = description
    return ou


def get_ou(ou_id):
    ou = db.session.get(OrganisationalUnit, ou_id)
    if not ou:
        raise NotFound("OU not found")
    return ou


def active_fields(ou, scope):
    return [f for f in ou.custom_fields if f.scope == scope and f.is_active]


def _validate_field_payload(data):
    if data.get("field_type") not in FIELD_TYPES:
        raise AppError(f"field_type must be one of {', '.join(FIELD_TYPES)}", 422)
    if data["field_type"] == "select" and not data.get("options"):
        raise AppError("Select fields need at least one option", 422)


def add_field(ou, data):
    _validate_field_payload(data)
    key = data.get("field_key") or slugify(data["label"])
    if not key:
        raise AppError("Could not derive a field key from the label", 422)
    if db.session.query(OUCustomField).filter_by(ou_id=ou.id, scope=data["scope"], field_key=key).first():
        raise AppError(f"A {data['scope']} field with key '{key}' already exists for this OU", 409)
    order = max([f.display_order for f in ou.custom_fields] or [-1]) + 1
    field = OUCustomField(ou_id=ou.id, scope=data["scope"], field_key=key, label=data["label"].strip(),
                          field_type=data["field_type"], is_required=data.get("is_required", False),
                          options=data.get("options") or None, display_order=data.get("display_order", order))
    db.session.add(field)
    db.session.flush()
    return field


def update_field(field, data):
    merged = {"field_type": data.get("field_type", field.field_type),
              "options": data.get("options", field.options)}
    _validate_field_payload(merged)
    for attr in ("label", "field_type", "is_required", "options", "display_order", "is_active"):
        if attr in data:
            setattr(field, attr, data[attr])
    return field


# ------------------------------------------------------------------------- Domain
def create_domain(name, code, description=None):
    if _ci_exists(Domain, Domain.name, name):
        raise AppError("A domain with this name already exists", 409)
    if _ci_exists(Domain, Domain.code, code):
        raise AppError("A domain with this code already exists", 409)
    d = Domain(name=name.strip(), code=code.strip().upper(), description=description)
    db.session.add(d)
    db.session.flush()
    return d


def update_domain(domain, name=None, description=None):
    if name and name.strip().lower() != domain.name.lower():
        if _ci_exists(Domain, Domain.name, name, domain.id):
            raise AppError("A domain with this name already exists", 409)
        domain.name = name.strip()
    if description is not None:
        domain.description = description
    return domain


def add_subdomain(domain, name):
    name = (name or "").strip()
    if len(name) < 2:
        raise AppError("Subdomain name is required", 422, {"name": "At least 2 characters"})
    if db.session.query(Subdomain).filter(Subdomain.domain_id == domain.id,
                                          db.func.lower(Subdomain.name) == name.lower()).first():
        raise AppError(f"'{name}' already exists in {domain.name}", 409, {"name": "Already exists in this domain"})
    sd = Subdomain(domain_id=domain.id, name=name)
    db.session.add(sd)
    db.session.flush()
    return sd


def update_subdomain(sd, name=None, is_active=None):
    if name is not None:
        name = name.strip()
        if db.session.query(Subdomain).filter(Subdomain.domain_id == sd.domain_id, Subdomain.id != sd.id,
                                              db.func.lower(Subdomain.name) == name.lower()).first():
            raise AppError(f"'{name}' already exists in this domain", 409, {"name": "Already exists in this domain"})
        sd.name = name
    if is_active is not None:
        sd.is_active = is_active
    return sd


def get_domain(domain_id):
    d = db.session.get(Domain, domain_id)
    if not d:
        raise NotFound("Domain not found")
    return d


def set_domain_leads(domain, user_ids):
    users = db.session.query(User).filter(User.id.in_(user_ids or [-1])).all() if user_ids else []
    if len(users) != len(set(user_ids or [])):
        raise AppError("One or more users do not exist", 422)
    if any(u.role_name != "domain_lead" for u in users):
        raise AppError("Only users with the Domain Lead role can be assigned as leads", 422)
    wanted = {u.id for u in users}
    for link in list(domain.leads):
        if link.user_id not in wanted:
            domain.leads.remove(link)
    have = {l.user_id for l in domain.leads}
    for uid in wanted - have:
        domain.leads.append(DomainLead(user_id=uid, domain_id=domain.id))
    return domain


# -------------------------------------------------------------------------- Batch
def get_batch_or_404(batch_id):
    b = db.session.get(Batch, batch_id)
    if not b:
        raise NotFound("Batch not found")
    return b


def validate_batch_data(ou, data, existing=None):
    """Validate a batch payload against the OU's configured fields.

    Returns (clean, errors). `errors` maps field name -> message; `clean` is None when invalid.
    Shared by the create/update API and the bulk importer so rules cannot drift.
    """
    errors, clean = {}, {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code:
        errors["code"] = "Batch code is required"
    elif len(code) > 50:
        errors["code"] = "Batch code must be at most 50 characters"
    elif _ci_exists(Batch, Batch.code, code, existing.id if existing else None):
        errors["code"] = f"Batch code '{code}' already exists"
    if not name:
        errors["name"] = "Batch name is required"
    clean.update(code=code, name=name[:150])

    domain = None
    if data.get("domain_id"):
        domain = db.session.get(Domain, data["domain_id"])
    if not domain:
        errors["domain"] = "A valid domain is required"
    elif not domain.is_active:
        errors["domain"] = f"Domain '{domain.name}' is inactive"
    clean["domain_id"] = domain.id if domain else None

    for key in ("start_date", "end_date"):
        raw = data.get(key)
        if raw in (None, ""):
            clean[key] = None
            continue
        try:
            clean[key] = parse_date(raw)
        except ValueError as e:
            errors[key] = str(e)
    if clean.get("start_date") and clean.get("end_date") and clean["end_date"] < clean["start_date"]:
        errors["end_date"] = "End date cannot be before start date"

    details = {}
    incoming = data.get("details") or {}
    fields = active_fields(ou, "batch")
    known = {f.field_key for f in fields}
    for unknown in set(incoming) - known:
        errors[f"details.{unknown}"] = "Unknown field for this OU"
    for f in fields:
        value, err = validate_custom_value(f, incoming.get(f.field_key))
        if err:
            errors[f"details.{f.field_key}"] = err
        elif value is not None:
            details[f.field_key] = value
    clean["details"] = details
    return (None if errors else clean), errors


def _apply_details(batch, ou, details):
    fields = {f.field_key: f for f in active_fields(ou, "batch")}
    existing = {d.field_id: d for d in batch.ou_details}
    for key, field in fields.items():
        value = details.get(key)
        row = existing.get(field.id)
        if value is None:
            if row:
                batch.ou_details.remove(row)
        elif row:
            row.value = value
        else:
            batch.ou_details.append(BatchOUDetail(field_id=field.id, value=value))


def new_batch_code(domain_id):
    """System-issued batch ID: ICT_<DOMAIN SHORT CODE>_<6 mixed letters/digits>, e.g. ICT_AIML_7K3Q9X."""
    domain = db.session.get(Domain, domain_id) if domain_id else None
    kind = re.sub(r"[^A-Za-z0-9]", "", domain.code).upper() if domain else "BATCH"
    return generate_id(kind, lambda c: _ci_exists(Batch, Batch.code, c))


def create_batch(data):
    # The batch ID is always system-generated (any code sent by the client is ignored).
    data = {**data, "code": new_batch_code(data.get("domain_id"))}
    ou = get_ou(data["ou_id"])
    if not ou.is_active:
        raise AppError("Cannot create a batch under an inactive OU", 422)
    clean, errors = validate_batch_data(ou, data)
    if errors:
        raise AppError("Validation failed", 422, errors)
    return build_batch(ou, clean)


def build_batch(ou, clean):
    batch = Batch(code=clean["code"], name=clean["name"], ou_id=ou.id, domain_id=clean["domain_id"],
                  start_date=clean["start_date"], end_date=clean["end_date"])
    db.session.add(batch)
    db.session.flush()
    _apply_details(batch, ou, clean["details"])
    return batch


def update_batch(batch, data):
    data = {k: v for k, v in data.items() if k != "code"}  # the generated batch ID never changes
    if data.get("ou_id") and data["ou_id"] != batch.ou_id:
        raise AppError("A batch's OU cannot be changed after creation", 422)
    merged = {"code": batch.code, "name": batch.name, "domain_id": batch.domain_id,
              "start_date": batch.start_date, "end_date": batch.end_date,
              "details": {d.field.field_key: d.value for d in batch.ou_details}}
    merged.update({k: v for k, v in data.items() if k in merged and k != "details"})
    if "details" in data:
        merged["details"] = {**merged["details"], **data["details"]}
    clean, errors = validate_batch_data(batch.ou, merged, existing=batch)
    if errors:
        raise AppError("Validation failed", 422, errors)
    batch.code, batch.name, batch.domain_id = clean["code"], clean["name"], clean["domain_id"]
    batch.start_date, batch.end_date = clean["start_date"], clean["end_date"]
    _apply_details(batch, batch.ou, clean["details"])
    return batch


def set_project_dates(batch, start_raw, end_raw):
    start, end = parse_date(start_raw), parse_date(end_raw)
    errors = {}
    if not start:
        errors["project_start_date"] = "A valid project start date (YYYY-MM-DD) is required"
    if not end:
        errors["project_end_date"] = "A valid project end date (YYYY-MM-DD) is required"
    if start and end and end <= start:
        errors["project_end_date"] = "The project end date must be after the start date"
    if errors:
        raise AppError("Validation failed", 422, errors)
    batch.project_start_date, batch.project_end_date = start, end
    return batch


def delete_batch(batch, actor, with_students=False):
    """Permanently delete a batch. Refused while it has projects (that would destroy project work); students must be
    removed first unless `with_students` is set, which also deletes their accounts. Returns what was removed."""
    from app.models import Project
    from app.services import user_service
    projects = db.session.query(Project).filter_by(batch_id=batch.id).count()
    if projects:
        raise AppError(f"This batch has {projects} project(s). Close the batch instead of deleting it.", 409)
    students = db.session.query(Student).filter_by(batch_id=batch.id).all()
    if students and not with_students:
        raise AppError(f"This batch has {len(students)} student(s). Delete them first, or choose to delete them with the batch.", 409,
                       {"student_count": len(students)})
    for s in students:
        user_service.delete_user(s.user, actor)
    info = {"code": batch.code, "name": batch.name, "students_deleted": len(students)}
    db.session.delete(batch)  # batch mentors and OU detail values cascade
    db.session.flush()
    return info


def set_batch_status(batch, status):
    if status not in ("active", "closed"):
        raise AppError("status must be 'active' or 'closed'", 422)
    batch.status = status
    return batch


def batch_student_count(batch_id):
    return db.session.query(db.func.count(Student.id)).filter_by(batch_id=batch_id).scalar()
