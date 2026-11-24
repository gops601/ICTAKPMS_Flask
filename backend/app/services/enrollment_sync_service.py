"""Enrol batches and students from another portal.

Payload (the same shape for a push from the portal and for a pull we make):

    {"batches": [{"code": "EXT-101", "name": "Full Stack Jan", "domain": "AIML", "ou": "ICTAK" (optional),
                  "start_date": "2026-01-05", "end_date": "2026-06-30",
                  "students": [{"name": "Asha K", "email": "asha@x.com", "registration_no": "R1", "phone": "999"}]}]}

`code` is the portal's own batch id; it is remembered so later syncs update the same batch instead of duplicating it.
Re-running a sync is safe: batches are matched by (portal, code) and students by e-mail.
"""
import json
import urllib.error
import urllib.request

from app.extensions import db
from app.models import Batch, Domain, OrganisationalUnit, Student, User
from app.models.base import utcnow
from app.services import domain_sync_service, org_service, user_service
from app.services.fields import parse_date
from app.services.notification_service import domain_lead_user_ids, domain_mentor_user_ids, notify
from app.utils.errors import AppError

MAX_BATCHES, MAX_STUDENTS = 200, 5000


def _find_domain(value):
    value = (value or "").strip()
    if not value:
        return None
    return (db.session.query(Domain).filter(db.or_(db.func.lower(Domain.code) == value.lower(),
                                                   db.func.lower(Domain.name) == value.lower())).first())


def _find_ou(portal, value):
    value = (value or "").strip()
    if value:
        ou = (db.session.query(OrganisationalUnit).filter(db.or_(db.func.lower(OrganisationalUnit.code) == value.lower(),
                                                                db.func.lower(OrganisationalUnit.name) == value.lower())).first())
        if ou:
            return ou
    if portal.default_ou_id:
        return db.session.get(OrganisationalUnit, portal.default_ou_id)
    return db.session.query(OrganisationalUnit).filter_by(is_active=True).order_by(OrganisationalUnit.id).first()


def _new_batch(portal, item, actor):
    domain = _find_domain(item.get("domain"))
    if not domain:
        raise AppError(f"domain '{item.get('domain') or ''}' was not found here - create it first or fix the domain code")
    ou = _find_ou(portal, item.get("ou"))
    if not ou:
        raise AppError("no organisational unit is available for the new batch")
    details = dict(item.get("details") or {})
    for f in org_service.active_fields(ou, "batch"):      # required free-text fields the portal cannot know are filled in
        if f.is_required and f.field_type == "text" and not details.get(f.field_key):
            details[f.field_key] = f"Imported from {portal.name}"
    try:
        batch = org_service.create_batch({"name": item.get("name") or item["code"], "ou_id": ou.id, "domain_id": domain.id,
                                          "start_date": item.get("start_date"), "end_date": item.get("end_date"),
                                          "details": details})
    except AppError as e:
        detail = "; ".join(f"{k}: {v}" for k, v in (e.errors or {}).items())
        raise AppError(f"{e.message}{' (' + detail + ')' if detail else ''} - send the OU's required batch fields under 'details'")
    batch.external_portal_id, batch.external_ref = portal.id, str(item["code"])[:100]
    db.session.flush()
    notify(domain_lead_user_ids(batch.domain_id), "batch_assigned", "Batch enrolled from " + portal.name,
           f"Batch {batch.code} - {batch.name} was enrolled from {portal.name} into {domain.name}. "
           "Please set the project start and end dates for this batch.", f"/lead/batches/{batch.id}")
    notify(domain_mentor_user_ids(batch.domain_id), "batch_in_domain", "New batch in your domain",
           f"Batch {batch.code} - {batch.name} was added to {domain.name}.", None)
    if actor is not None:
        domain_sync_service.auto_assign_mentors(batch, actor)
    domain_sync_service.warn_admins_if_no_lead(batch.domain_id, f"Batch {batch.code}")
    return batch


def _enrol_student(batch, row, summary):
    email = (row.get("email") or "").strip().lower()
    name = (row.get("name") or "").strip()
    if not email or "@" not in email:
        raise AppError(f"student '{name or '?'}' has no valid e-mail")
    user = db.session.query(User).filter(db.func.lower(User.email) == email).first()
    if user is None:
        if len(name) < 2:
            raise AppError(f"{email}: name is required")
        user_service.create_student(batch, name, email, (row.get("phone") or None), row.get("registration_no"))
        summary["students_created"] += 1
        return
    student = db.session.query(Student).filter_by(user_id=user.id).first()
    if not student:
        raise AppError(f"{email} already exists as a {user.role_name}, not a student")
    if student.batch_id != batch.id:
        raise AppError(f"{email} is already enrolled in batch {student.batch.code}")
    if name:
        user.name = name[:150]
    if row.get("phone"):
        user.phone = str(row["phone"])[:30]
    summary["students_updated"] += 1


def apply(portal, payload, actor):
    """Apply an enrolment payload; returns a summary (problems are listed, never abort the whole sync)."""
    batches = payload.get("batches") if isinstance(payload, dict) else None
    if not isinstance(batches, list):
        raise AppError('Payload must look like {"batches": [...]}', 422)
    if len(batches) > MAX_BATCHES or sum(len(b.get("students") or []) for b in batches if isinstance(b, dict)) > MAX_STUDENTS:
        raise AppError("Payload is too large", 413)
    summary = {"batches_created": 0, "batches_updated": 0, "students_created": 0, "students_updated": 0, "problems": []}
    for item in batches:
        code = str(item.get("code") or "").strip() if isinstance(item, dict) else ""
        if not code:
            summary["problems"].append("A batch without a 'code' was skipped")
            continue
        item["code"] = code
        try:
            with db.session.begin_nested():
                batch = db.session.query(Batch).filter_by(external_portal_id=portal.id, external_ref=code).first()
                if batch is None:
                    batch = _new_batch(portal, item, actor)
                    summary["batches_created"] += 1
                else:
                    if item.get("name"):
                        batch.name = str(item["name"])[:150]
                    for key in ("start_date", "end_date"):
                        if item.get(key):
                            setattr(batch, key, parse_date(item[key]))
                    summary["batches_updated"] += 1
                for row in item.get("students") or []:
                    try:
                        with db.session.begin_nested():
                            _enrol_student(batch, row if isinstance(row, dict) else {}, summary)
                    except AppError as e:
                        summary["problems"].append(f"Batch {code}: {e.message}")
        except (AppError, ValueError) as e:
            summary["problems"].append(f"Batch {code}: {getattr(e, 'message', None) or e}")
    portal.last_sync_at, portal.last_sync_summary = utcnow(), summary
    return summary


def pull(portal, actor):
    """Fetch the portal's enrolment feed (GET base_url + enrollment_path) and apply it."""
    if not portal.base_url:
        raise AppError("This portal has no base URL, so there is nothing to pull from. Ask the portal to push instead.", 422)
    url = portal.base_url.rstrip("/") + "/" + (portal.enrollment_path or "").lstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        raise AppError("The portal URL must start with http:// or https://", 422)
    headers = {"Accept": "application/json"}
    if portal.api_token:
        headers["Authorization"] = f"Bearer {portal.api_token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:  # noqa: S310 - scheme checked
            payload = json.loads(resp.read(20 * 1024 * 1024))
    except urllib.error.HTTPError as e:
        raise AppError(f"{portal.name} answered {e.code} {e.reason}", 502)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise AppError(f"Could not read the enrolment feed from {portal.name}: {getattr(e, 'reason', e)}", 502)
    return apply(portal, payload, actor)
