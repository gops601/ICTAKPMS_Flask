"""Validation of OU-configurable (dynamic) field values, shared by forms and imports."""
import re
from datetime import date, datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIELD_TYPES = ("text", "number", "date", "select", "email")
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y")


def parse_date(value):
    """Accept date objects, ISO strings, common dd/mm/yyyy forms and Excel 'YYYY-MM-DD HH:MM:SS'."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d", text):
        text = text[:10]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{value}' is not a valid date (use YYYY-MM-DD)")


def validate_custom_value(field, raw):
    """Return (stored_string_or_None, error_or_None) for one OU custom field value."""
    value = "" if raw is None else str(raw).strip()
    if value == "":
        return (None, f"{field.label} is required") if field.is_required else (None, None)
    if len(value) > 500:
        return None, f"{field.label} must be at most 500 characters"
    kind = field.field_type
    if kind == "number":
        try:
            float(value)
        except ValueError:
            return None, f"{field.label} must be a number"
    elif kind == "date":
        try:
            value = parse_date(value).isoformat()
        except ValueError as e:
            return None, f"{field.label}: {e}"
    elif kind == "email":
        if not EMAIL_RE.match(value):
            return None, f"{field.label} must be a valid email"
    elif kind == "select":
        options = field.options or []
        match = next((o for o in options if str(o).lower() == value.lower()), None)
        if match is None:
            return None, f"{field.label} must be one of: {', '.join(map(str, options))}"
        value = str(match)
    return value, None
