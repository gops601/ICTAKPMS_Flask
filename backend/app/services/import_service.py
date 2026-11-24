"""Generic bulk-import engine (parse -> validate -> stage -> preview -> confirm) with importers.

Flow: `preview()` parses and validates every row and stores an ImportJob (valid rows staged in
`payload`, failures in ImportError). Nothing is written to the real tables until `confirm()`.
Invalid rows are never imported silently: confirm refuses while errors exist unless the caller
explicitly asks to import only the valid rows.
"""
import csv
import io
import re

import pandas as pd

from app.extensions import db
from app.models import (Batch, Domain, ImportError as ImportRowError, ImportJob, ProblemStatement, Student, User)
from app.services import org_service, problem_service, user_service
from app.services.fields import EMAIL_RE, validate_custom_value
from app.utils.errors import AppError, NotFound

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
PREVIEW_ROWS = 100


# --------------------------------------------------------------------- column specs
def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def batch_columns(ou):
    cols = [
        {"header": "Batch Code", "key": "code", "required": True},
        {"header": "Batch Name", "key": "name", "required": True},
        {"header": "Domain Code", "key": "domain", "required": True},
        {"header": "Batch Mode", "key": "mode", "required": False},
        {"header": "Start Date", "key": "start_date", "required": False},
        {"header": "End Date", "key": "end_date", "required": False},
    ]
    for f in org_service.active_fields(ou, "batch"):
        cols.append({"header": f.label, "key": f"details.{f.field_key}", "required": f.is_required, "field": f})
    return cols


def student_columns(ou):
    cols = [
        {"header": "Student Name", "key": "name", "required": True},
        {"header": "Email", "key": "email", "required": True},
        {"header": "Phone Number", "key": "phone", "required": False},
        {"header": "Registration Number", "key": "registration_no", "required": True},
        {"header": "Batch Code", "key": "batch_code", "required": True},
    ]
    for f in org_service.active_fields(ou, "student"):
        cols.append({"header": f.label, "key": f"extra.{f.field_key}", "required": f.is_required, "field": f})
    return cols


def _aliases(col):
    names = {_norm(col["header"]), _norm(col["key"].split(".")[-1])}
    return names


# ------------------------------------------------------------------------- parsing
def read_upload(filename, content):
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xlsx"):
        raise AppError("Only .csv and .xlsx files are supported", 422)
    if not content:
        raise AppError("The uploaded file is empty", 422)
    if len(content) > MAX_IMPORT_BYTES:
        raise AppError("File is too large (max 5 MB)", 413)
    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8-sig")
        else:
            df = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False, engine="openpyxl")
    except Exception as exc:  # malformed file of any kind
        raise AppError(f"Could not read the file: {exc.__class__.__name__}", 422)
    if len(df) > MAX_IMPORT_ROWS:
        raise AppError(f"Too many rows (max {MAX_IMPORT_ROWS})", 422)
    return df


def _map_columns(df, columns):
    """Map file headers to column specs; return (key -> header_in_file, missing_required, ignored)."""
    file_headers = {_norm(h): h for h in df.columns}
    mapping, missing = {}, []
    for col in columns:
        hit = next((file_headers[a] for a in _aliases(col) if a in file_headers), None)
        if hit is None:
            if col["required"]:
                missing.append(col["header"])
        else:
            mapping[col["key"]] = hit
    used = set(mapping.values())
    ignored = [h for h in df.columns if h not in used]
    return mapping, missing, ignored


# -------------------------------------------------------------------------- importers
class BatchImporter:
    type = "batches"

    def columns(self, ou):
        return batch_columns(ou)

    def validate(self, ou, rows, user=None):
        """rows: list of (row_number, dict). Returns list of (row_number, clean|None, [(field,msg)])."""
        domains = {d.code.lower(): d for d in db.session.query(Domain).all()}
        seen, out = {}, []
        for rn, raw in rows:
            errs = []
            domain_code = (raw.get("domain") or "").strip()
            domain = domains.get(domain_code.lower()) if domain_code else None
            data = {"code": raw.get("code"), "name": raw.get("name"), "domain_id": domain.id if domain else None, "mode": raw.get("mode"),
                    "start_date": raw.get("start_date"), "end_date": raw.get("end_date"),
                    "details": {k.split(".", 1)[1]: v for k, v in raw.items() if k.startswith("details.")}}
            clean, field_errors = org_service.validate_batch_data(ou, data)
            for k, msg in field_errors.items():
                if k == "domain" and domain_code and domain is None:
                    msg = f"Domain code '{domain_code}' does not exist"
                errs.append((k, msg))
            code_key = (raw.get("code") or "").strip().lower()
            if code_key:
                if code_key in seen:
                    errs.append(("code", f"Duplicate batch code '{raw.get('code').strip()}' (first seen on row {seen[code_key]})"))
                else:
                    seen[code_key] = rn
            if errs:
                out.append((rn, None, errs))
            else:
                clean = dict(clean)
                for k in ("start_date", "end_date"):
                    clean[k] = clean[k].isoformat() if clean[k] else None
                out.append((rn, clean, []))
        return out

    def commit(self, ou, payload_rows, actor):
        from datetime import date
        created = 0
        for item in payload_rows:
            d = dict(item["data"])
            for k in ("start_date", "end_date"):
                d[k] = date.fromisoformat(d[k]) if d[k] else None
            # Re-check at commit time: another request may have taken the code since preview.
            if org_service._ci_exists(Batch, Batch.code, d["code"]):
                raise AppError(f"Batch code '{d['code']}' was created by someone else; re-upload the file", 409)
            org_service.build_batch(ou, d)
            created += 1
        return created, None


class StudentImporter:
    type = "students"

    def columns(self, ou):
        return student_columns(ou)

    def validate(self, ou, rows, user=None):
        batches = {b.code.lower(): b for b in db.session.query(Batch).filter_by(ou_id=ou.id).all()}
        fields = {f.field_key: f for f in org_service.active_fields(ou, "student")}
        existing_emails = {e[0].lower() for e in db.session.query(User.email).all()}
        existing_regs = {(s.batch_id, s.registration_no.lower()) for s in db.session.query(Student).all()}
        seen_email, seen_reg, out = {}, {}, []
        for rn, raw in rows:
            errs = []
            name = (raw.get("name") or "").strip()
            email = (raw.get("email") or "").strip().lower()
            reg = (raw.get("registration_no") or "").strip()
            batch_code = (raw.get("batch_code") or "").strip()
            phone = (raw.get("phone") or "").strip()
            if len(name) < 2:
                errs.append(("name", "Student name is required (min 2 characters)"))
            if not email:
                errs.append(("email", "Email is required"))
            elif not EMAIL_RE.match(email):
                errs.append(("email", f"'{email}' is not a valid email"))
            elif email in existing_emails:
                errs.append(("email", f"Email '{email}' is already registered"))
            elif email in seen_email:
                errs.append(("email", f"Duplicate email in file (first seen on row {seen_email[email]})"))
            else:
                seen_email[email] = rn
            if len(phone) > 30:
                errs.append(("phone", "Phone number is too long"))
            batch = batches.get(batch_code.lower()) if batch_code else None
            if not batch_code:
                errs.append(("batch_code", "Batch code is required"))
            elif batch is None:
                errs.append(("batch_code", f"Batch '{batch_code}' not found in {ou.name}"))
            if not reg:
                errs.append(("registration_no", "Registration number is required"))
            elif batch is not None:
                key = (batch.id, reg.lower())
                if key in existing_regs:
                    errs.append(("registration_no", f"Registration number '{reg}' already exists in batch {batch.code}"))
                elif key in seen_reg:
                    errs.append(("registration_no", f"Duplicate registration number in file (row {seen_reg[key]})"))
                else:
                    seen_reg[key] = rn
            extra = {}
            for key, f in fields.items():
                value, err = validate_custom_value(f, raw.get(f"extra.{key}"))
                if err:
                    errs.append((f"extra.{key}", err))
                elif value is not None:
                    extra[key] = value
            if errs:
                out.append((rn, None, errs))
            else:
                out.append((rn, {"name": name, "email": email, "phone": phone or None, "registration_no": reg,
                                 "batch_id": batch.id, "extra": extra}, []))
        return out

    def commit(self, ou, payload_rows, actor):
        credentials = []
        for item in payload_rows:
            d = item["data"]
            batch = db.session.get(Batch, d["batch_id"])
            student, pw = user_service.create_student(batch, d["name"], d["email"], d["phone"],
                                                      d["registration_no"], d["extra"])
            credentials.append(user_service.credential_row(student, pw))
        return len(credentials), credentials


PS_COLUMNS = [
    ("Problem Statement ID", "ps_code", True), ("Project Title", "title", True), ("Domain Code", "domain", True),
    ("Description", "description", False), ("Problem Definition", "problem_definition", False),
    ("Objectives", "objectives", False), ("Scope", "scope", False), ("Expected Outcomes", "expected_outcomes", False),
    ("Functional Requirements", "functional_requirements", False),
    ("Non-Functional Requirements", "non_functional_requirements", False),
    ("Suggested Technologies", "suggested_technologies", False), ("Dataset Information", "dataset_info", False),
    ("Difficulty Level", "difficulty", False), ("Duration", "estimated_duration", False),
    ("Required Skills", "required_skills", False), ("Status", "status", False),
    ("Statement Type", "source_type", False), ("Industry", "industry", False), ("Subdomain", "subdomain", False),
]


class ProblemStatementImporter:
    """Not OU-specific. Datasets/documents are attached separately (never embedded in cells)."""
    type = "problem_statements"

    def columns(self, ou=None):
        return [{"header": h, "key": k, "required": r} for h, k, r in PS_COLUMNS]

    def validate(self, ou, rows, user=None):
        domains = {d.code.lower(): d for d in db.session.query(Domain).all()}
        seen, out = {}, []
        for rn, raw in rows:
            errs = []
            code = (raw.get("domain") or "").strip()
            domain = domains.get(code.lower()) if code else None
            data = {k: raw.get(k) for _, k, _ in PS_COLUMNS if k not in ("domain", "subdomain") and raw.get(k) not in (None, "")}
            data["domain_id"] = domain.id if domain else None
            sub_name = (raw.get("subdomain") or "").strip()
            if sub_name and domain:
                match = next((s for s in domain.subdomains if s.name.lower() == sub_name.lower()), None)
                if match is None:
                    errs.append(("subdomain_id", f"Subdomain '{sub_name}' does not exist in {domain.name}"))
                else:
                    data["subdomain_id"] = match.id
            data["ps_code"] = raw.get("ps_code")
            clean, field_errors = problem_service.validate_ps_data(data, user)
            for k, msg in field_errors.items():
                if k == "domain" and code and domain is None:
                    msg = f"Domain code '{code}' does not exist"
                errs.append((k, msg))
            key = (raw.get("ps_code") or "").strip().lower()
            if key:
                if key in seen:
                    errs.append(("ps_code", f"Duplicate ID in file (first seen on row {seen[key]})"))
                else:
                    seen[key] = rn
            out.append((rn, None, errs) if errs else (rn, clean, []))
        return out

    def commit(self, ou, payload_rows, actor):
        for item in payload_rows:
            d = item["data"]
            if db.session.query(ProblemStatement).filter(
                    db.func.lower(ProblemStatement.ps_code) == d["ps_code"].lower()).first():
                raise AppError(f"ID '{d['ps_code']}' was created by someone else; re-upload the file", 409)
            problem_service.create_ps(d, actor)
        return len(payload_rows), None


IMPORTERS = {"batches": BatchImporter(), "students": StudentImporter(),
             "problem_statements": ProblemStatementImporter()}


def get_importer(import_type):
    imp = IMPORTERS.get(import_type)
    if not imp:
        raise NotFound(f"Unknown import type '{import_type}'")
    return imp


# ---------------------------------------------------------------------------- engine
def preview(import_type, ou, filename, content, user):
    importer = get_importer(import_type)
    df = read_upload(filename, content)
    columns = importer.columns(ou)
    mapping, missing, ignored = _map_columns(df, columns)
    if missing:
        raise AppError("The file is missing required columns: " + ", ".join(missing), 422,
                       {"missing_columns": missing})

    rows = []
    for idx, rec in df.iterrows():
        if all(str(v).strip() == "" for v in rec.values):
            continue  # skip fully blank lines
        raw = {key: str(rec[header]).strip() for key, header in mapping.items()}
        rows.append((int(idx) + 2, raw))  # +2: header is row 1
    if not rows:
        raise AppError("The file contains no data rows", 422)

    results = importer.validate(ou, rows, user)
    job = ImportJob(import_type=import_type, ou_id=ou.id if ou else None, user_id=user.id, filename=filename[:255],
                    total_rows=len(results))
    db.session.add(job)
    db.session.flush()
    payload, preview_rows = [], []
    header_of = {c["key"]: c["header"] for c in columns}  # error reports reuse the template's headers
    raw_by_row = dict(rows)
    for rn, clean, errs in results:
        if errs:
            for field, msg in errs:
                db.session.add(ImportRowError(
                    job_id=job.id, row_number=rn, field=header_of.get(field, field), message=msg[:500],
                    row_data={header_of[k]: v for k, v in raw_by_row[rn].items()}))
        else:
            payload.append({"row_number": rn, "data": clean})
        if len(preview_rows) < PREVIEW_ROWS:
            preview_rows.append({"row_number": rn, "status": "error" if errs else "valid",
                                 "data": raw_by_row[rn], "errors": [{"field": f, "message": m} for f, m in errs]})
    job.valid_rows = len(payload)
    job.error_rows = job.total_rows - len(payload)
    job.payload = payload
    db.session.commit()
    return job, preview_rows, ignored


def confirm(job, user, import_valid_only=False):
    if job.user_id != user.id:
        raise NotFound("Import job not found")
    if job.status != "previewed":
        raise AppError(f"This import was already {job.status}", 409)
    if job.error_rows and not import_valid_only:
        raise AppError(f"{job.error_rows} row(s) failed validation. Fix the file and re-upload, or confirm "
                       "importing only the valid rows.", 409)
    if not job.valid_rows:
        raise AppError("There are no valid rows to import", 409)
    importer = get_importer(job.import_type)
    ou = org_service.get_ou(job.ou_id) if job.ou_id else None
    try:
        count, extra = importer.commit(ou, job.payload, user)
        job.status = "confirmed"
        job.imported_rows = count
        job.payload = None  # staged data (and anything sensitive) is dropped after commit
        from app.utils.audit import audit
        audit(user.id, f"import.{job.import_type}", "import_job", job.id,
              {"imported": count, "skipped": job.error_rows, "ou_id": job.ou_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return job, extra


def errors_csv(job):
    out = io.StringIO()
    keys = []
    for e in job.errors:
        for k in (e.row_data or {}):
            if k not in keys:
                keys.append(k)
    w = csv.writer(out)
    w.writerow(["row_number", "field", "error"] + keys)
    for e in sorted(job.errors, key=lambda x: x.row_number):
        w.writerow([e.row_number, e.field, e.message] + [_csv_safe((e.row_data or {}).get(k, "")) for k in keys])
    return out.getvalue()


def _csv_safe(value):
    """Neutralise spreadsheet formula injection in downloadable reports."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s
