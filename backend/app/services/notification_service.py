"""In-app notifications. Callers own the transaction; nothing here commits."""
from app.extensions import db
from app.models import DomainLead, Notification


def notify(user_ids, type_, title, message=None, link=None):
    """Create one notification per distinct user id (None / duplicates ignored)."""
    for uid in {u for u in user_ids if u}:
        db.session.add(Notification(user_id=uid, type=type_, title=title[:200], message=message, link=link))


def domain_lead_user_ids(domain_id):
    if not domain_id:
        return set()
    return {r[0] for r in db.session.query(DomainLead.user_id).filter_by(domain_id=domain_id).all()}


def domain_mentor_user_ids(domain_id):
    """Active mentors who belong to a domain."""
    if not domain_id:
        return set()
    from app.models import Mentor, User
    from app.services.domain_sync_service import mentor_in_domains
    rows = (db.session.query(Mentor.user_id).join(User, User.id == Mentor.user_id)
            .filter(mentor_in_domains([domain_id]), User.is_active.is_(True)).all())
    return {r[0] for r in rows}
