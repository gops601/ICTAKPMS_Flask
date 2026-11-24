from marshmallow import EXCLUDE, Schema, fields, validate


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class OUSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    code = fields.String(required=True, validate=validate.Regexp(r"^[A-Za-z0-9_-]{2,30}$"))
    description = fields.String(load_default=None)


class OUUpdateSchema(_Base):
    name = fields.String(validate=validate.Length(min=2, max=120))
    description = fields.String(allow_none=True)


class FieldSchema(_Base):
    label = fields.String(required=True, validate=validate.Length(min=1, max=120))
    field_key = fields.String(validate=validate.Regexp(r"^[a-z0-9_]{1,60}$"))
    scope = fields.String(load_default="batch", validate=validate.OneOf(["batch", "student"]))
    field_type = fields.String(load_default="text", validate=validate.OneOf(["text", "number", "date", "select", "email"]))
    is_required = fields.Boolean(load_default=False)
    options = fields.List(fields.String(validate=validate.Length(min=1, max=100)), allow_none=True)
    display_order = fields.Integer()


class FieldUpdateSchema(_Base):
    label = fields.String(validate=validate.Length(min=1, max=120))
    field_type = fields.String(validate=validate.OneOf(["text", "number", "date", "select", "email"]))
    is_required = fields.Boolean()
    options = fields.List(fields.String(validate=validate.Length(min=1, max=100)), allow_none=True)
    display_order = fields.Integer()
    is_active = fields.Boolean()


class DomainSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    code = fields.String(required=True, validate=validate.Regexp(r"^[A-Za-z0-9_-]{2,30}$"))
    description = fields.String(load_default=None)


class DomainUpdateSchema(_Base):
    name = fields.String(validate=validate.Length(min=2, max=120))
    description = fields.String(allow_none=True)


class SubdomainSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))


class SubdomainUpdateSchema(_Base):
    name = fields.String(validate=validate.Length(min=2, max=120))
    is_active = fields.Boolean()


class DomainLeadsSchema(_Base):
    user_ids = fields.List(fields.Integer(), required=True)


class BatchSchema(_Base):
    code = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=50))  # blank = generated ICT_BATCH_ id
    name = fields.String(required=True, validate=validate.Length(min=1, max=150))
    ou_id = fields.Integer(required=True)
    domain_id = fields.Integer(required=True)
    mode = fields.String(load_default="online", validate=validate.OneOf(["online", "offline"]))   # online = 4 weeks, offline = 3 weeks
    start_date = fields.String(allow_none=True)
    end_date = fields.String(allow_none=True)
    details = fields.Dict(keys=fields.String(), values=fields.Raw(allow_none=True), load_default=dict)


class BatchUpdateSchema(_Base):
    code = fields.String(validate=validate.Length(min=1, max=50))
    name = fields.String(validate=validate.Length(min=1, max=150))
    ou_id = fields.Integer()
    domain_id = fields.Integer()
    mode = fields.String(validate=validate.OneOf(["online", "offline"]))
    start_date = fields.String(allow_none=True)
    end_date = fields.String(allow_none=True)
    details = fields.Dict(keys=fields.String(), values=fields.Raw(allow_none=True))


class ProjectDatesSchema(_Base):
    project_start_date = fields.String(required=True)
    project_end_date = fields.String(required=True)


class StatusSchema(_Base):
    status = fields.String(required=True)


class ActiveSchema(_Base):
    is_active = fields.Boolean(required=True)


class StudentCreateSchema(_Base):
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    email = fields.Email(required=True)
    phone = fields.String(load_default=None, validate=validate.Length(max=30))
    registration_no = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=60))  # blank = generated ICT_STU_ id
    batch_id = fields.Integer(required=True)
    extra_fields = fields.Dict(load_default=dict)


class CredentialsSchema(_Base):
    batch_id = fields.Integer(required=True)
    student_ids = fields.List(fields.Integer(), load_default=None)


class StaffCreateSchema(_Base):
    role = fields.String(required=True, validate=validate.OneOf(["admin", "domain_lead", "mentor"]))
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    email = fields.Email(required=True)
    phone = fields.String(load_default=None, validate=validate.Length(max=30))
    password = fields.String(load_default=None, validate=validate.Length(max=128))
    domain_id = fields.Integer(load_default=None)
    domain_ids = fields.List(fields.Integer(), load_default=None)  # domain leads: the domain(s) they lead (required)
    designation = fields.String(load_default=None, validate=validate.Length(max=120))
    expertise = fields.String(load_default=None, validate=validate.Length(max=255))
    mentor_type = fields.String(load_default="internal", validate=validate.OneOf(["internal", "industry"]))
    company = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=150))
    industry_sector = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=120))
    experience_years = fields.Integer(load_default=None, allow_none=True, validate=validate.Range(min=0, max=70))
    linkedin_url = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))
    bio = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=5000))


class LeadDomainsSchema(_Base):
    domain_ids = fields.List(fields.Integer(), required=True)


class StaffCredentialsSchema(_Base):
    role = fields.String(required=True, validate=validate.OneOf(["mentor", "domain_lead"]))
    user_ids = fields.List(fields.Integer(), load_default=None)
    include_active = fields.Boolean(load_default=False)  # also reissue for people who already set their own password


class ResetPasswordAdminSchema(_Base):
    new_password = fields.String(load_default=None, validate=validate.Length(max=128))


def _iso(d):
    return d.isoformat() if d else None


def field_to_dict(f):
    return {"id": f.id, "ou_id": f.ou_id, "scope": f.scope, "field_key": f.field_key, "label": f.label,
            "field_type": f.field_type, "is_required": f.is_required, "options": f.options,
            "display_order": f.display_order, "is_active": f.is_active}


def ou_to_dict(ou, with_fields=False):
    d = {"id": ou.id, "name": ou.name, "code": ou.code, "description": ou.description, "is_active": ou.is_active}
    if with_fields:
        d["fields"] = [field_to_dict(f) for f in ou.custom_fields]
    return d


def subdomain_to_dict(s):
    return {"id": s.id, "domain_id": s.domain_id, "name": s.name, "is_active": s.is_active}


def domain_to_dict(d, counts=None):
    out = {"id": d.id, "name": d.name, "code": d.code, "description": d.description, "is_active": d.is_active,
           "leads": [{"id": l.user.id, "name": l.user.name, "email": l.user.email} for l in d.leads],
           "subdomains": [subdomain_to_dict(s) for s in d.subdomains]}
    if counts:
        out.update(counts)
    return out


def batch_to_dict(b, student_count=None, details=True):
    out = {"id": b.id, "code": b.code, "name": b.name, "status": b.status, "mode": b.mode, "total_weeks": 3 if b.mode == "offline" else 4,
           "ou": {"id": b.ou.id, "name": b.ou.name}, "domain": {"id": b.domain.id, "name": b.domain.name} if b.domain else None,
           "start_date": _iso(b.start_date), "end_date": _iso(b.end_date),
           "project_start_date": _iso(b.project_start_date), "project_end_date": _iso(b.project_end_date)}
    if student_count is not None:
        out["student_count"] = student_count
    if details:
        out["details"] = {d.field.field_key: d.value for d in b.ou_details}
    return out


def student_to_dict(s):
    return {"id": s.id, "user_id": s.user_id, "name": s.user.name, "email": s.user.email, "phone": s.user.phone,
            "is_active": s.user.is_active, "registration_no": s.registration_no, "extra_fields": s.extra_fields or {},
            "batch": {"id": s.batch.id, "code": s.batch.code, "name": s.batch.name, "mode": s.batch.mode}}


def mentor_to_dict(m):
    return {"id": m.id, "user_id": m.user_id, "name": m.user.name, "email": m.user.email, "phone": m.user.phone,
            "is_active": m.user.is_active, "designation": m.designation, "expertise": m.expertise,
            "mentor_type": m.mentor_type, "company": m.company, "industry_sector": m.industry_sector,
            "experience_years": m.experience_years, "linkedin_url": m.linkedin_url, "bio": m.bio,
            "is_domain_lead": m.user.role_name == "domain_lead",
            "domain": {"id": m.domain.id, "name": m.domain.name} if m.domain else None}
