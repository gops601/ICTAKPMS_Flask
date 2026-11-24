"""Keep everything that belongs to a domain connected, without anyone having to remember to do it.

* A new batch automatically gets the domain lead(s) of its domain as mentors (a lead is a mentor by default).
  Other mentors are never added automatically: the admin / lead adds them explicitly on the batch.
* A new domain lead (who is also a mentor) is added to every active batch of the domains they lead.
* Whenever something is created under a domain that has no lead, the administrators are told (nobody would see it).
* `repair()` (run at startup via `flask sync-data`) heals batches that ended up with no mentor and reports leads
  without a domain and domains without a lead. It never re-adds a mentor a lead deliberately removed from a batch that
  still has other mentors.
"""
from app.extensions import db
from app.models import Batch, BatchMentor, Domain, DomainLead, Mentor, Role, User
from app.services import project_service
from app.services.notification_service import domain_lead_user_ids, notify


def mentor_in_domains(domain_ids):
    """SQL condition: mentors of these domains, including domain leads (who are mentors of every domain they lead)."""
    ids = list(domain_ids) or [-1]
    return db.or_(Mentor.domain_id.in_(ids), Mentor.user_id.in_(db.select(DomainLead.user_id).where(DomainLead.domain_id.in_(ids))))


def mentor_domain_ids(mentor):
    """Domains a mentor serves: their own, plus every domain they lead."""
    ids = {r[0] for r in db.session.query(DomainLead.domain_id).filter_by(user_id=mentor.user_id)}
    if mentor.domain_id:
        ids.add(mentor.domain_id)
    return ids


def ensure_lead_mentor_profile(user, domain_id=None):
    """A domain lead is also a mentor: give them a mentor profile (idempotent). Returns (mentor, created)."""
    mentor = db.session.query(Mentor).filter_by(user_id=user.id).first()
    if mentor:
        if domain_id and not mentor.domain_id:
            mentor.domain_id = domain_id
        return mentor, False
    mentor = Mentor(user_id=user.id, domain_id=domain_id, designation="Domain Lead", mentor_type="internal")
    db.session.add(mentor)
    db.session.flush()
    return mentor, True


def domain_mentors(domain_id):
    if not domain_id:
        return []
    return (db.session.query(Mentor).join(User, User.id == Mentor.user_id)
            .filter(mentor_in_domains([domain_id]), User.is_active.is_(True)).all())


def lead_mentors(domain_id):
    """Active mentor profiles of the domain's lead(s): the only mentors a batch gets by default."""
    if not domain_id:
        return []
    return (db.session.query(Mentor).join(User, User.id == Mentor.user_id)
            .filter(Mentor.user_id.in_(db.select(DomainLead.user_id).where(DomainLead.domain_id == domain_id)),
                    User.is_active.is_(True)).all())


def _active_mentor_ids(batch_id):
    return {l.mentor_id for l in db.session.query(BatchMentor).filter_by(batch_id=batch_id, is_active=True)}


def auto_assign_mentors(batch, actor):
    """Put the batch's domain lead(s) on the batch as mentors. Returns the mentors added."""
    if not batch.domain_id or batch.status != "active":
        return []
    on_batch = _active_mentor_ids(batch.id)
    added = [m for m in lead_mentors(batch.domain_id) if m.id not in on_batch]
    for m in added:
        project_service.assign_batch_mentor(batch, m, actor)
    if added:
        notify(domain_lead_user_ids(batch.domain_id), "batch_mentors_auto", "Mentors assigned to your batch",
               f"{', '.join(m.user.name for m in added)} {'was' if len(added) == 1 else 'were'} automatically assigned to "
               f"batch {batch.code} as its mentor (domain lead of {batch.domain.name}). You can add more mentors on the batch page.",
               f"/lead/batches/{batch.id}")
    return added


def auto_assign_mentor_to_batches(mentor, actor):
    """A domain lead (as a mentor) joins every active batch of the domains they lead; other mentors are not auto-added."""
    domains = {r[0] for r in db.session.query(DomainLead.domain_id).filter_by(user_id=mentor.user_id)}
    if not domains:
        return []
    joined = []
    batches = db.session.query(Batch).filter(Batch.domain_id.in_(domains), Batch.status == "active").all()
    for b in batches:
        if mentor.id not in _active_mentor_ids(b.id):
            project_service.assign_batch_mentor(b, mentor, actor)
            joined.append(b)
    if joined:
        notify(domain_lead_user_ids(batches[0].domain_id) - {mentor.user_id}, "batch_mentors_auto", "New mentor assigned to your batches",
               f"{mentor.user.name} was automatically assigned to {', '.join(b.code for b in joined)}.", "/lead/batches")
    return joined


def warn_admins_if_no_lead(domain_id, what):
    """Anything created under a domain with no lead is invisible to leads: tell the administrators."""
    if not domain_id or domain_lead_user_ids(domain_id):
        return False
    domain = db.session.get(Domain, domain_id)
    admins = {r[0] for r in db.session.query(User.id).join(Role, Role.id == User.role_id)
              .filter(Role.name == "admin", User.is_active.is_(True)).all()}
    notify(admins, "domain_without_lead", "Domain has no lead",
           f"{what} was added to {domain.name}, but that domain has no domain lead yet, so nobody can see it. "
           "Create or assign a lead for it.", "/admin/domain-leads")
    return True


def repair(actor):
    """Idempotent startup self-heal. Returns a report of what was fixed and what needs an administrator."""
    report = {"batches_given_mentors": [], "leads_without_domain": [], "domains_without_lead": [], "mentors_without_domain": []}
    if actor is not None:
        for b in db.session.query(Batch).filter_by(status="active").all():
            if b.domain_id and not _active_mentor_ids(b.id):
                added = auto_assign_mentors(b, actor)
                if added:
                    report["batches_given_mentors"].append((b.code, [m.user.email for m in added]))
    leads = (db.session.query(User).join(Role, Role.id == User.role_id).filter(Role.name == "domain_lead").all())
    with_domain = {r[0] for r in db.session.query(DomainLead.user_id).all()}
    if actor is not None:                    # every domain lead is also a mentor: backfill leads created before that rule
        for u in leads:
            if u.id in with_domain and u.is_active:
                first = db.session.query(DomainLead.domain_id).filter_by(user_id=u.id).order_by(DomainLead.id).first()
                mentor, created = ensure_lead_mentor_profile(u, first[0] if first else None)
                if created:
                    auto_assign_mentor_to_batches(mentor, actor)
                    report.setdefault("leads_made_mentors", []).append(u.email)
    report["leads_without_domain"] = [u.email for u in leads if u.id not in with_domain]
    led = {r[0] for r in db.session.query(DomainLead.domain_id).all()}
    in_use = {r[0] for r in db.session.query(Batch.domain_id).filter(Batch.domain_id.isnot(None)).all()}
    report["domains_without_lead"] = [d.name for d in db.session.query(Domain).filter(Domain.id.in_(in_use or {-1})).all() if d.id not in led]
    report["mentors_without_domain"] = [m.user.email for m in db.session.query(Mentor).filter(Mentor.domain_id.is_(None)).all()]
    return report
