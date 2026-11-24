"""Detailed data-collection sheet that students fill in (Excel) when they propose a project with datasets.

`build_template()` makes the downloadable workbook (instructions + an example sheet); `parse()` reads the filled one
and returns one validated dict per dataset. The parsed rows are stored on the proposal and copied to the Project Shelf.
"""
import io

from openpyxl import Workbook, load_workbook

from app.utils.errors import AppError

MAX_ROWS = 50
SHEET = "Data collection"
SOURCES = ["Own collection", "Public / open data", "Client / industry", "Web scraping / API", "Synthetic", "Other"]
DATA_TYPES = ["Tabular", "Text", "Image", "Audio", "Video", "Time series", "Geospatial", "Mixed"]
YES_NO = ["Yes", "No"]

# key, header, required, kind, options/notes, example
COLUMNS = [
    ("name", "Dataset Name", True, "text", None, "Student attendance records"),
    ("description", "Description", True, "text", None, "Daily attendance of 120 students captured from the classroom camera"),
    ("source", "Source", True, "select", SOURCES, "Own collection"),
    ("source_url", "Source URL", False, "text", None, "https://example.org/dataset"),
    ("data_type", "Data Type", True, "select", DATA_TYPES, "Tabular"),
    ("file_format", "File Format", True, "text", None, "CSV"),
    ("records", "Number of Records", True, "int", None, 12000),
    ("features", "Number of Features / Columns", True, "int", None, 8),
    ("feature_names", "Column / Feature Names", True, "text", None, "student_id, date, status, confidence"),
    ("target", "Target Variable", False, "text", None, "status"),
    ("collection_method", "Collection Method", True, "text", None, "Camera frames labelled by two reviewers"),
    ("collection_period", "Collection Period", False, "text", None, "Jan 2026 - Mar 2026"),
    ("license", "License / Usage Rights", True, "text", None, "Internal use only"),
    ("personal_data", "Contains Personal Data", True, "select", YES_NO, "Yes"),
    ("privacy", "Privacy / Anonymisation", False, "text", None, "Names replaced by IDs"),
    ("limitations", "Known Limitations", False, "text", None, "Few samples of night-time lighting"),
]
_BY_HEADER = {c[1].lower(): c for c in COLUMNS}


def _widths(ws):
    for i, c in enumerate(COLUMNS, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(18, len(c[1]) + 6)


def build_template():
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append([c[1] + (" *" if c[2] else "") for c in COLUMNS])
    _widths(ws)
    ws.freeze_panes = "A2"
    ex = wb.create_sheet("Example")
    ex.append([c[1] + (" *" if c[2] else "") for c in COLUMNS])
    ex.append([c[5] for c in COLUMNS])
    _widths(ex)
    guide = wb.create_sheet("Instructions")
    guide.append(["Fill one row per dataset in the 'Data collection' sheet (max %d). Columns marked * are required." % MAX_ROWS])
    guide.append([])
    guide.append(["Column", "Required", "Notes"])
    for key, header, required, kind, opts, _ex in COLUMNS:
        note = {"int": "Whole number", "select": "One of: " + ", ".join(opts or [])}.get(kind, "Free text")
        guide.append([header, "Yes" if required else "No", note])
    guide.column_dimensions["A"].width = 34
    guide.column_dimensions["C"].width = 70
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse(file_storage):
    """Read an uploaded sheet. Raises AppError(422) listing every problem found (with row numbers)."""
    if not file_storage or not file_storage.filename.lower().endswith(".xlsx"):
        raise AppError("Upload the data collection sheet as an .xlsx file (download the template first)", 422,
                       {"data_sheet": "Must be an .xlsx file"})
    stream = file_storage.stream
    stream.seek(0)
    try:
        wb = load_workbook(stream, read_only=True, data_only=True)
    except Exception:
        raise AppError("The data collection sheet could not be read. Use the template (.xlsx).", 422, {"data_sheet": "Unreadable file"})
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    stream.seek(0)
    if not rows:
        raise AppError("The data collection sheet is empty", 422, {"data_sheet": "Empty sheet"})
    index = {}
    for pos, head in enumerate(rows[0]):
        col = _BY_HEADER.get(str(head or "").replace("*", "").strip().lower())
        if col:
            index[col[0]] = pos
    missing = [c[1] for c in COLUMNS if c[2] and c[0] not in index]
    if missing:
        raise AppError("Missing column(s): " + ", ".join(missing) + ". Use the template.", 422, {"data_sheet": "Columns missing"})
    out, problems = [], []
    for n, row in enumerate(rows[1:], start=2):
        if not any(str(v).strip() for v in row if v is not None):
            continue
        item = {}
        for key, header, required, kind, opts, _ex in COLUMNS:
            raw = row[index[key]] if key in index and index[key] < len(row) else None
            text = "" if raw is None else str(raw).strip()
            if not text:
                if required:
                    problems.append(f"Row {n}: {header} is required")
                item[key] = None
                continue
            if kind == "int":
                try:
                    val = int(float(text))
                    if val < 0 or float(text) != val:
                        raise ValueError
                    item[key] = val
                except ValueError:
                    problems.append(f"Row {n}: {header} must be a whole number")
                    item[key] = None
            elif kind == "select":
                match = next((o for o in opts if o.lower() == text.lower()), None)
                if not match:
                    problems.append(f"Row {n}: {header} must be one of {', '.join(opts)}")
                item[key] = match
            else:
                item[key] = text[:2000]
        out.append(item)
        if len(out) > MAX_ROWS:
            raise AppError(f"At most {MAX_ROWS} datasets per sheet", 422, {"data_sheet": "Too many rows"})
    if not out and not problems:
        problems.append("The sheet has no dataset rows")
    if problems:
        shown = problems[:8] + ([f"…and {len(problems) - 8} more"] if len(problems) > 8 else [])
        raise AppError("Data collection sheet has problems: " + "; ".join(shown), 422, {"data_sheet": "; ".join(shown)})
    return out
