"""Problem statement business rules (shared by the API and the bulk importer)."""
import re

import bleach

from app.extensions import db
from app.models import Domain, ProblemStatement
from app.permissions.scope import can_access_domain
from app.utils.errors import AppError, NotFound

DIFFICULTIES = ("easy", "medium", "hard")
STATUSES = ("active", "inactive")
SOURCE_TYPES = ("internal", "industry")
RICH_FIELDS = ("description", "problem_definition", "objectives", "scope", "expected_outcomes",
               "functional_requirements", "non_functional_requirements", "suggested_technologies",
               "dataset_info", "required_skills")
FIELD_LABELS = {
    "description": "Project description", "problem_definition": "Problem definition",
    "objectives": "Project objectives", "scope": "Scope", "expected_outcomes": "Expected outcomes",
    "functional_requirements": "Functional requirements",
    "non_functional_requirements": "Non-functional requirements",
    "suggested_technologies": "Suggested technologies", "dataset_info": "Dataset information",
    "required_skills": "Required skills",
}
MAX_TEXT = 50000
PS_CODE_RE = re.compile(r"^[A-Za-z0-9._-]{1,50}$")

_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote",
         "code", "pre", "a", "table", "thead", "tbody", "tr", "th", "td", "hr", "span"]
_ATTRS = {"a": ["href", "title", "rel"]}
_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(value):
    """Rich text is stored as HTML; strip scripts, handlers and unsafe URLs on the way in."""
    cleaned = bleach.clean(value or "", tags=_TAGS, attributes=_ATTRS, protocols=_PROTOCOLS, strip=True)
    return bleach.linkify(cleaned, callbacks=[bleach.callbacks.nofollow], skip_tags=["pre", "code"])


def validate_ps_data(data, user, existing=None):
    """Return (clean, errors). `errors` maps field -> message; `clean` is None when invalid."""
    errors, clean = {}, {}

    code = (data.get("ps_code") or "").strip() if not existing else existing.ps_code
    if not existing:
        if not code:
            errors["ps_code"] = "Problem statement ID is required"
        elif not PS_CODE_RE.match(code):
            errors["ps_code"] = "ID may only contain letters, numbers, '.', '_' and '-' (max 50)"
        elif db.session.query(ProblemStatement).filter(db.func.lower(ProblemStatement.ps_code) == code.lower()).first():
            errors["ps_code"] = f"Problem statement ID '{code}' already exists"
    clean["ps_code"] = code

    title = (data.get("title") if "title" in data or not existing else existing.title) or ""
    title = title.strip()
    if not title:
        errors["title"] = "Project title is required"
    elif len(title) > 255:
        errors["title"] = "Project title must be at most 255 characters"
    clean["title"] = title

    domain_id = data.get("domain_id", existing.domain_id if existing else None)
    domain = db.session.get(Domain, domain_id) if domain_id else None
    if not domain:
        errors["domain"] = "A valid domain is required"
    elif not can_access_domain(user, domain.id):
        errors["domain"] = f"You do not have access to domain '{domain.name}'"
    elif not domain.is_active and (not existing or existing.domain_id != domain.id):
        errors["domain"] = f"Domain '{domain.name}' is inactive"
    clean["domain_id"] = domain.id if domain else None

    difficulty = str(data.get("difficulty", existing.difficulty if existing else "medium") or "medium").strip().lower()
    if difficulty not in DIFFICULTIES:
        errors["difficulty"] = f"Difficulty must be one of: {', '.join(DIFFICULTIES)}"
    clean["difficulty"] = difficulty

    status = str(data.get("status", existing.status if existing else "active") or "active").strip().lower()
    if status not in STATUSES:
        errors["status"] = f"Status must be one of: {', '.join(STATUSES)}"
    clean["status"] = status

    source_type = str(data.get("source_type", existing.source_type if existing else "internal") or "internal").strip().lower()
    if source_type not in SOURCE_TYPES:
        errors["source_type"] = "Statement type must be internal or industry"
    clean["source_type"] = source_type
    industry = data.get("industry", existing.industry if existing else None)
    industry = str(industry).strip() if industry not in (None, "") else None
    if source_type == "industry":
        if not industry:
            errors["industry"] = "Industry is required for an industry problem statement"
        elif len(industry) > 120:
            errors["industry"] = "Industry must be at most 120 characters"
    else:
        industry = None  # internal statements carry no industry
    clean["industry"] = industry

    duration = data.get("estimated_duration", existing.estimated_duration if existing else None)
    duration = (str(duration).strip() if duration not in (None, "") else None)
    if duration and len(duration) > 60:
        errors["estimated_duration"] = "Estimated duration must be at most 60 characters"
    clean["estimated_duration"] = duration

    for f in RICH_FIELDS:
        raw = data.get(f, getattr(existing, f) if existing else None)
        raw = "" if raw is None else str(raw)
        if len(raw) > MAX_TEXT:
            errors[f] = f"{FIELD_LABELS[f]} is too long (max {MAX_TEXT} characters)"
        clean[f] = sanitize_html(raw) or None
    if not clean.get("description") and not clean.get("problem_definition"):
        errors["description"] = "Provide a project description or a problem definition"
    return (None if errors else clean), errors


def get_ps_or_404(ps_id):
    ps = db.session.get(ProblemStatement, ps_id)
    if not ps:
        raise NotFound("Problem statement not found")
    return ps


def create_ps(clean, user):
    ps = ProblemStatement(created_by=user.id, **clean)
    db.session.add(ps)
    db.session.flush()
    return ps


def update_ps(ps, data, user):
    if "ps_code" in data and data["ps_code"].strip().lower() != ps.ps_code.lower():
        raise AppError("A problem statement ID cannot be changed after creation", 422)
    clean, errors = validate_ps_data(data, user, existing=ps)
    if errors:
        raise AppError("Validation failed", 422, errors)
    for k, v in clean.items():
        setattr(ps, k, v)
    return ps


def set_status(ps, status):
    if status not in STATUSES:
        raise AppError(f"status must be one of: {', '.join(STATUSES)}", 422)
    ps.status = status
    return ps
