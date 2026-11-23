from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Batch, Domain, Student, Subdomain
from app.permissions import current_user, roles_required
from app.permissions.scope import lead_domain_ids
from app.schemas.org import (ActiveSchema, DomainLeadsSchema, DomainSchema, DomainUpdateSchema, SubdomainSchema,
                             SubdomainUpdateSchema, domain_to_dict, subdomain_to_dict)
from app.services import org_service
from app.utils.audit import audit
from app.utils.errors import NotFound
from app.utils.responses import ok

bp = Blueprint("domains", __name__, url_prefix="/api/domains", description="Domains")
SEC = [{"bearerAuth": []}]


def _counts(domain_ids):
    if not domain_ids:
        return {}
    batch_counts = dict(db.session.query(Batch.domain_id, db.func.count(Batch.id))
                        .filter(Batch.domain_id.in_(domain_ids)).group_by(Batch.domain_id).all())
    student_counts = dict(db.session.query(Batch.domain_id, db.func.count(Student.id))
                          .join(Student, Student.batch_id == Batch.id)
                          .filter(Batch.domain_id.in_(domain_ids)).group_by(Batch.domain_id).all())
    return {i: {"batch_count": batch_counts.get(i, 0), "student_count": student_counts.get(i, 0)}
            for i in domain_ids}


def _visible(user, domain_id):
    return user.role_name == "admin" or domain_id in lead_domain_ids(user)


@bp.get("")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def list_domains():
    user = current_user()
    q = db.select(Domain).order_by(Domain.name)
    if user.role_name == "domain_lead":
        q = q.where(Domain.id.in_(lead_domain_ids(user) or {-1}))
    if request.args.get("active") in ("1", "true"):
        q = q.where(Domain.is_active.is_(True))
    domains = list(db.session.scalars(q))
    counts = _counts([d.id for d in domains])
    return ok([domain_to_dict(d, counts[d.id]) for d in domains])


@bp.post("")
@bp.doc(security=SEC)
@bp.arguments(DomainSchema)
@roles_required("admin")
def create_domain(data):
    d = org_service.create_domain(data["name"], data["code"], data["description"])
    audit(current_user().id, "domain.create", "domain", d.id)
    db.session.commit()
    return ok(domain_to_dict(d), "Domain created", 201)


@bp.get("/<int:domain_id>")
@bp.doc(security=SEC)
@roles_required("admin", "domain_lead")
def get_domain(domain_id):
    if not _visible(current_user(), domain_id):
        raise NotFound("Domain not found")
    d = org_service.get_domain(domain_id)
    return ok(domain_to_dict(d, _counts([d.id])[d.id]))


@bp.put("/<int:domain_id>")
@bp.doc(security=SEC)
@bp.arguments(DomainUpdateSchema)
@roles_required("admin")
def update_domain(data, domain_id):
    d = org_service.update_domain(org_service.get_domain(domain_id), data.get("name"), data.get("description"))
    audit(current_user().id, "domain.update", "domain", d.id)
    db.session.commit()
    return ok(domain_to_dict(d))


@bp.patch("/<int:domain_id>/active")
@bp.doc(security=SEC)
@bp.arguments(ActiveSchema)
@roles_required("admin")
def set_active(data, domain_id):
    d = org_service.get_domain(domain_id)
    d.is_active = data["is_active"]
    audit(current_user().id, "domain.activate" if d.is_active else "domain.deactivate", "domain", d.id)
    db.session.commit()
    return ok(domain_to_dict(d))


@bp.put("/<int:domain_id>/leads")
@bp.doc(security=SEC)
@bp.arguments(DomainLeadsSchema)
@roles_required("admin")
def set_leads(data, domain_id):
    d = org_service.set_domain_leads(org_service.get_domain(domain_id), data["user_ids"])
    audit(current_user().id, "domain.set_leads", "domain", d.id, {"user_ids": data["user_ids"]})
    db.session.commit()
    return ok(domain_to_dict(d), "Domain leads updated")


# ------------------------------------------------------------------ subdomains
@bp.get("/<int:domain_id>/subdomains")
@bp.doc(security=SEC, description="Subdomains of a domain (admins, the domain's leads, and mentors of its batches).")
@roles_required("admin", "domain_lead", "mentor")
def list_subdomains(domain_id):
    from app.permissions.scope import mentor_domain_ids
    user = current_user()
    if user.role_name == "mentor":
        if domain_id not in mentor_domain_ids(user):
            raise NotFound("Domain not found")
    elif not _visible(user, domain_id):
        raise NotFound("Domain not found")
    d = org_service.get_domain(domain_id)
    items = [s for s in d.subdomains if s.is_active or request.args.get("all") in ("1", "true")]
    return ok([subdomain_to_dict(s) for s in items])


@bp.post("/<int:domain_id>/subdomains")
@bp.doc(security=SEC, description="Add a subdomain. Admins, or a lead of that domain (e.g. while creating a project).")
@bp.arguments(SubdomainSchema)
@roles_required("admin", "domain_lead")
def add_subdomain(data, domain_id):
    user = current_user()
    if not _visible(user, domain_id):
        raise NotFound("Domain not found")
    sd = org_service.add_subdomain(org_service.get_domain(domain_id), data["name"])
    audit(user.id, "subdomain.create", "domain", domain_id, {"name": sd.name})
    db.session.commit()
    return ok(subdomain_to_dict(sd), "Subdomain added", 201)


@bp.patch("/subdomains/<int:subdomain_id>")
@bp.doc(security=SEC, description="Rename or (de)activate a subdomain.")
@bp.arguments(SubdomainUpdateSchema)
@roles_required("admin", "domain_lead")
def update_subdomain(data, subdomain_id):
    user = current_user()
    sd = db.session.get(Subdomain, subdomain_id)
    if not sd or not _visible(user, sd.domain_id):
        raise NotFound("Subdomain not found")
    org_service.update_subdomain(sd, data.get("name"), data.get("is_active"))
    audit(user.id, "subdomain.update", "domain", sd.domain_id, {"subdomain_id": sd.id})
    db.session.commit()
    return ok(subdomain_to_dict(sd))
