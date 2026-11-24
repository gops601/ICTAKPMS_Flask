"""Downloadable CSV/XLSX import templates, generated from the OU's current field configuration."""
import io

from openpyxl import Workbook

from app.services.import_service import get_importer


def build_template(import_type, ou, fmt):
    cols = get_importer(import_type).columns(ou)
    headers = [c["header"] for c in cols]
    if fmt == "csv":
        return (",".join(f'"{h}"' for h in headers) + "\n").encode("utf-8-sig"), "text/csv"

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(headers)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(16, len(h) + 4)
    if import_type == "batches":
        _batch_dropdowns(wb, ws, cols)
    guide = wb.create_sheet("Instructions")
    guide.append(["Column", "Required", "Notes"])
    for c in cols:
        field = c.get("field")
        note = {"date": "YYYY-MM-DD", "number": "Numeric", "email": "Valid email",
                "select": "One of: " + ", ".join(map(str, field.options or []))}.get(field.field_type, "") if field else ""
        if c["key"] == "domain":
            note = "Pick the domain from the dropdown (its short code also works)"
        elif c["key"] == "domain_id":
            note = "Filled in automatically from the domain; do not type here"
        elif c["key"] == "mode":
            note = "online (4 weeks) or offline (3 weeks). Default online"
        elif c["key"] == "difficulty":
            note = "easy, medium or hard (default medium)"
        elif c["key"] == "status":
            note = "active or inactive (default active)"
        elif c["key"] == "subdomain":
            note = "Pick from the dropdown (depends on the domain). Optional for batches; required for problem statements when the domain has subdomains"
        elif c["key"] == "source_type":
            note = "internal or industry (default internal)"
        elif c["key"] == "industry":
            note = "Required when Statement Type is industry, e.g. Healthcare"
        elif c["key"] == "ps_code":
            note = "Unique ID, letters/numbers/. _ - only"
        elif c["key"] in ("description", "problem_definition"):
            note = "Provide at least one of Description / Problem Definition. HTML is allowed (sanitised)"
        if c["key"] in ("start_date", "end_date"):
            note = "YYYY-MM-DD"
        guide.append([c["header"], "Yes" if c["required"] else "No", note])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


BATCH_ROWS = 500


def _batch_dropdowns(wb, ws, cols):
    """Domain Name / SubDomain dropdowns from the portal's data, and a formula that fills the Domain ID."""
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from app.extensions import db
    from app.models import Domain, Subdomain

    idx = {c["key"]: i + 1 for i, c in enumerate(cols)}
    domains = db.session.query(Domain).filter_by(is_active=True).order_by(Domain.name).all()
    lists = wb.create_sheet("Lists")
    lists["A1"], lists["B1"] = "Domain Name", "Domain ID"
    for i, d in enumerate(domains, 2):
        lists.cell(row=i, column=1, value=d.name)
        lists.cell(row=i, column=2, value=d.id)
    for j, d in enumerate(domains):
        lists.cell(row=1, column=4 + j, value=d.name)
        subs = db.session.query(Subdomain).filter_by(domain_id=d.id, is_active=True).order_by(Subdomain.name).all()
        for i, s in enumerate(subs, 2):
            lists.cell(row=i, column=4 + j, value=s.name)
    n = max(len(domains), 1) + 1
    last = get_column_letter(4 + max(len(domains), 1))
    dom, did, sub = (get_column_letter(idx[k]) for k in ("domain", "domain_id", "subdomain"))
    last_row = BATCH_ROWS + 1

    dv = DataValidation(type="list", formula1=f"=Lists!$A$2:$A${n}", allow_blank=True, showErrorMessage=True,
                        errorTitle="Domain", error="Choose a domain from the list.")
    ws.add_data_validation(dv)
    dv.add(f"{dom}2:{dom}{last_row}")
    pos = f"MATCH(${dom}2,Lists!$D$1:${last}$1,0)-1"
    dv_sub = DataValidation(
        type="list", allow_blank=True, showErrorMessage=True, errorTitle="SubDomain",
        error="Choose a subdomain of the selected domain.",
        formula1=f"=OFFSET(Lists!$D$2,0,{pos},MAX(1,COUNTA(OFFSET(Lists!$D$2,0,{pos},100,1))),1)")
    ws.add_data_validation(dv_sub)
    dv_sub.add(f"{sub}2:{sub}{last_row}")
    dv_mode = DataValidation(type="list", formula1='"online,offline"', allow_blank=True)
    ws.add_data_validation(dv_mode)
    dv_mode.add(f"{get_column_letter(idx['mode'])}2:{get_column_letter(idx['mode'])}{last_row}")
    for r in range(2, last_row + 1):
        ws[f"{did}{r}"] = f'=IF({dom}{r}="","",IFERROR(INDEX(Lists!$B$2:$B${n},MATCH({dom}{r},Lists!$A$2:$A${n},0)),""))'
