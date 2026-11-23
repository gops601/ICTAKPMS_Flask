from datetime import datetime, timezone

from flask import Response, request
from flask_smorest import Blueprint

from app.extensions import db
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_batch_access
from app.services import dashboard_service, reporting
from app.utils.audit import audit
from app.utils.errors import AppError
from app.utils.responses import ok

bp = Blueprint("dashboard", __name__, url_prefix="/api", description="Role dashboards and reports")
SEC = [{"bearerAuth": []}]


@bp.get("/dashboard")
@bp.doc(security=SEC, description="Live, role-specific dashboard data (admin / domain lead / mentor / student).")
@login_required
def dashboard():
    """Optional ?batch_id= narrows admin / domain lead / mentor dashboards to one batch (404 if out of scope)."""
    user = current_user()
    filters = {}
    batch_id = request.args.get("batch_id", type=int)
    if batch_id and user.role_name != "student":
        ensure_batch_access(user, batch_id)
        filters["batch_id"] = batch_id
    return ok(dashboard_service.BUILDERS[user.role_name](user, filters))


@bp.get("/reports")
@bp.doc(security=SEC)
@login_required
def list_reports():
    return ok(reporting.available_reports(current_user()))


def _filters():
    a = request.args
    ints = {k: a.get(k, type=int) for k in ("ou_id", "domain_id", "batch_id", "mentor_id", "week")}
    return {**ints, "stage": a.get("stage"), "status": a.get("status")}


@bp.get("/reports/<report_type>")
@bp.doc(security=SEC, description="format=json (default, paginated preview) | csv | xlsx (full export). Scoped to the caller's role.")
@login_required
def report(report_type):
    user = current_user()
    data = reporting.build(user, report_type, _filters())
    fmt = request.args.get("format", "json")
    if fmt in ("csv", "xlsx"):
        audit(user.id, "report.export", "report", None, {"type": report_type, "format": fmt, "rows": len(data["rows"])})
        from app.extensions import db
        db.session.commit()
        stamp = data["generated_at"][:10]
        if fmt == "csv":
            body, mime = reporting.to_csv(data), "text/csv; charset=utf-8"
        else:
            body, mime = reporting.to_xlsx(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(body, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{report_type}_{stamp}.{fmt}"',
                                                      "X-Content-Type-Options": "nosniff"})
    page = max(request.args.get("page", 1, type=int), 1)
    per = max(1, min(request.args.get("per_page", 25, type=int), 200))
    rows = data["rows"]
    total = len(rows)
    data["rows"] = rows[(page - 1) * per: page * per]
    return ok(data, meta={"page": page, "per_page": per, "total": total, "pages": max(1, -(-total // per))})


@bp.get("/reports/batch-detailed/<int:batch_id>")
@bp.doc(security=SEC, description="Detailed report for ONE batch (admin / domain lead of its domain): summary, every student's project "
                                  "status, weekly scores with remarks, per-criterion marks. format=xlsx (all sheets, default) | csv "
                                  "(sheet=students|weekly|criteria) | json.")
@roles_required("admin", "domain_lead")
def batch_detailed_report(batch_id):
    user = current_user()
    batch = ensure_batch_access(user, batch_id)
    data = reporting.batch_detailed(user, batch)
    fmt = request.args.get("format", "xlsx")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if fmt == "json":
        return ok({"batch": data["batch"], "summary": data["summary"],
                   "sheets": {k: {"columns": c, "rows": rows} for k, (c, rows) in data["sheets"].items()}})
    sheet = request.args.get("sheet", "students")
    if fmt == "csv" and sheet not in reporting.DETAILED_SHEETS:
        raise AppError("sheet must be students, weekly or criteria", 422)
    if fmt not in ("xlsx", "csv"):
        raise AppError("format must be xlsx, csv or json", 422)
    audit(user.id, "report.export", "batch", batch.id, {"type": "batch-detailed", "format": fmt})
    db.session.commit()
    if fmt == "csv":
        body, mime, ext = reporting.detailed_sheet_csv(data, sheet), "text/csv; charset=utf-8", f"{sheet}.csv"
    else:
        body, mime, ext = reporting.detailed_to_xlsx(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    return Response(body, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{batch.code}_detailed_report_{stamp}.{ext}"',
                                                  "X-Content-Type-Options": "nosniff"})
