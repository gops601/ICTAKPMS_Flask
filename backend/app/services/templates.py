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
    guide = wb.create_sheet("Instructions")
    guide.append(["Column", "Required", "Notes"])
    for c in cols:
        field = c.get("field")
        note = {"date": "YYYY-MM-DD", "number": "Numeric", "email": "Valid email",
                "select": "One of: " + ", ".join(map(str, field.options or []))}.get(field.field_type, "") if field else ""
        if c["key"] == "domain":
            note = "Use the domain code, e.g. AIML"
        elif c["key"] == "difficulty":
            note = "easy, medium or hard (default medium)"
        elif c["key"] == "status":
            note = "active or inactive (default active)"
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
