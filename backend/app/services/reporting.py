"""Tabular reports (JSON preview, CSV and XLSX export) built on the shared metrics engine and role scoping."""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Font

from app.extensions import db
from sqlalchemy.orm import selectinload

from app.models import (Batch, BatchMentor, Domain, EvaluationCriterion, Mentor, OrganisationalUnit, ProjectGithubRepository, ProjectReview, ProjectStudent,
                        ReviewStudentRemark, Student)
from app.permissions.scope import scoped_batches
from app.services import evaluation_service as ev
from app.services import lifecycle
from app.services.dashboard_service import load_projects, mentors_by_project, srs_status_of, SRS_LABELS
from app.services.metrics_service import project_metrics, review_score_map
from app.utils.errors import AppError, Forbidden

MAX_EXPORT_ROWS = 50000


def _safe(value):
    """Neutralise spreadsheet formula injection in exports."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _pct(a, b):
    return round(a * 100 / b, 1) if b else None


def _ctx(user, filters):
    projects = load_projects(user, filters)
    metrics = project_metrics(projects)
    mentors = mentors_by_project(projects)
    return projects, metrics, mentors


def _agg(projects, metrics):
    """Common aggregate columns for a group of projects."""
    return {
        "projects": len(projects),
        "completed": sum(1 for p in projects if p.stage == "completed"),
        "in_progress": sum(1 for p in projects if p.stage not in ("completed", "allocated")),
        "delayed": sum(1 for p in projects if metrics[p.id]["is_delayed"]),
        "avg_progress": _avg([metrics[p.id]["progress"] for p in projects]),
        "avg_score_pct": _avg([metrics[p.id]["score_pct"] for p in projects]),
    }


AGG_COLS = [("projects", "Projects"), ("completed", "Completed"), ("in_progress", "In progress"), ("delayed", "Delayed"),
            ("avg_progress", "Avg progress %"), ("avg_score_pct", "Avg evaluation %")]


def _cols(*pairs):
    return [{"key": k, "label": l} for k, l in pairs]


# ----------------------------------------------------------------- builders
def report_ou(user, f):
    projects, metrics, _ = _ctx(user, f)
    groups = defaultdict(list)
    for p in projects:
        groups[p.batch.ou_id].append(p)
    rows = []
    for ou in db.session.query(OrganisationalUnit).order_by(OrganisationalUnit.name):
        if f.get("ou_id") and ou.id != f["ou_id"]:
            continue
        batches = db.session.query(Batch).filter_by(ou_id=ou.id).count()
        students = db.session.query(Student).join(Batch, Batch.id == Student.batch_id).filter(Batch.ou_id == ou.id).count()
        rows.append({"ou": ou.name, "code": ou.code, "batches": batches, "students": students, **_agg(groups[ou.id], metrics)})
    return _cols(("ou", "OU"), ("code", "Code"), ("batches", "Batches"), ("students", "Students"), *AGG_COLS), rows


def report_domain(user, f):
    projects, metrics, _ = _ctx(user, f)
    groups = defaultdict(list)
    for p in projects:
        groups[p.batch.domain_id].append(p)
    visible = {b.domain_id for b in db.session.scalars(scoped_batches(user)) if b.domain_id}
    rows = []
    for d in db.session.query(Domain).order_by(Domain.name):
        if d.id not in visible and user.role_name != "admin":
            continue
        if f.get("domain_id") and d.id != f["domain_id"]:
            continue
        batches = db.session.query(Batch).filter_by(domain_id=d.id).count()
        students = db.session.query(Student).join(Batch, Batch.id == Student.batch_id).filter(Batch.domain_id == d.id).count()
        leads = ", ".join(sorted(l.user.name for l in d.leads)) or "—"
        rows.append({"domain": d.name, "leads": leads, "batches": batches, "students": students, **_agg(groups[d.id], metrics)})
    return _cols(("domain", "Domain"), ("leads", "Domain leads"), ("batches", "Batches"), ("students", "Students"), *AGG_COLS), rows


def report_batch(user, f):
    projects, metrics, _ = _ctx(user, f)
    groups = defaultdict(list)
    for p in projects:
        groups[p.batch_id].append(p)
    q = scoped_batches(user)
    if f.get("batch_id"):
        q = q.where(Batch.id == f["batch_id"])
    if f.get("ou_id"):
        q = q.where(Batch.ou_id == f["ou_id"])
    if f.get("domain_id"):
        q = q.where(Batch.domain_id == f["domain_id"])
    rows = []
    for b in db.session.scalars(q.order_by(Batch.code)):
        students = db.session.query(Student).filter_by(batch_id=b.id).count()
        rows.append({"code": b.code, "name": b.name, "ou": b.ou.name, "domain": b.domain.name if b.domain else "—", "status": b.status,
                     "students": students, **_agg(groups[b.id], metrics)})
    return _cols(("code", "Batch code"), ("name", "Batch"), ("ou", "OU"), ("domain", "Domain"), ("status", "Status"), ("students", "Students"), *AGG_COLS), rows


def report_student(user, f):
    projects, metrics, mentors = _ctx(user, f)
    by_student = {m.student_id: p for p in projects for m in p.members}
    q = db.select(Student).join(Batch, Batch.id == Student.batch_id).where(Batch.id.in_(scoped_batches(user).with_only_columns(Batch.id)))
    if f.get("batch_id"):
        q = q.where(Student.batch_id == f["batch_id"])
    if f.get("ou_id"):
        q = q.where(Batch.ou_id == f["ou_id"])
    if f.get("domain_id"):
        q = q.where(Batch.domain_id == f["domain_id"])
    rows = []
    for s in db.session.scalars(q.order_by(Batch.code, Student.registration_no)):
        p = by_student.get(s.id)
        if (f.get("stage") or f.get("mentor_id")) and not p:
            continue                       # these filters only make sense for students that have a project
        m = metrics[p.id] if p else None
        rows.append({
            "name": s.user.name, "registration_no": s.registration_no, "email": s.user.email, "batch": s.batch.code,
            "project": p.title if p else "Not allocated", "stage": lifecycle.LABELS[p.stage] if p else "—",
            "mentor": ", ".join(x.user.name for x in mentors[p.id]) if p else "—",
            "progress": m["progress"] if m else None, "srs": SRS_LABELS[srs_status_of(p.stage)] if p else "—",
            "github": "Yes" if m and m["has_github"] else "No" if p else "—",
            "tasks_done_pct": _pct(m["tasks"]["completed"], m["tasks"]["total"]) if m else None,
            "reviews_submitted": f"{m['reviews_submitted']}/4" if m else "—", "score_pct": m["score_pct"] if m else None,
            "delayed": ("Yes" if m["is_delayed"] else "No") if m else "—"})
    return _cols(("name", "Student"), ("registration_no", "Reg. no"), ("email", "Email"), ("batch", "Batch"), ("project", "Project"),
                 ("stage", "Stage"), ("mentor", "Mentor"), ("progress", "Progress %"), ("srs", "SRS"), ("github", "GitHub"),
                 ("tasks_done_pct", "Tasks done %"), ("reviews_submitted", "Reviews"), ("score_pct", "Overall score %"), ("delayed", "Delayed")), rows


def report_mentor(user, f):
    projects, metrics, mentors = _ctx(user, f)
    agg = defaultdict(lambda: {"projects": [], "batches": set()})
    for p in projects:
        for m in mentors[p.id]:
            agg[m.id]["projects"].append(p)
            agg[m.id]["batches"].add(p.batch.code)
    names = {m.id: m for m in db.session.query(Mentor).filter(Mentor.id.in_(list(agg) or [-1]))}
    rows = []
    for mid, a in agg.items():
        ps = a["projects"]
        submitted = sum(metrics[p.id]["reviews_submitted"] for p in ps)
        pending = sum(len(ev_pending(p, metrics[p.id])) for p in ps)
        rows.append({"mentor": names[mid].user.name, "email": names[mid].user.email, "batches": len(a["batches"]), "projects": len(ps),
                     "completed": sum(1 for p in ps if p.stage == "completed"),
                     "reviews_submitted": submitted, "reviews_pending": pending,
                     "reviews_overdue": sum(metrics[p.id]["reviews_overdue"] for p in ps),
                     "review_completion_pct": _pct(submitted, submitted + pending),
                     "avg_score_given_pct": _avg([metrics[p.id]["score_pct"] for p in ps]),
                     "delayed": sum(1 for p in ps if metrics[p.id]["is_delayed"])})
    rows.sort(key=lambda r: r["mentor"])
    return _cols(("mentor", "Mentor"), ("email", "Email"), ("batches", "Batches"), ("projects", "Projects"), ("completed", "Completed"),
                 ("reviews_submitted", "Reviews submitted"), ("reviews_pending", "Reviews pending"), ("reviews_overdue", "Reviews overdue"),
                 ("review_completion_pct", "Review completion %"), ("avg_score_given_pct", "Avg score given %"), ("delayed", "Delayed projects")), rows


def ev_pending(project, m):
    return [w for w, status in m["reviews"].items() if status != "submitted" and ev.week_gate(project, w) is None]


def report_weekly(user, f):
    projects, metrics, mentors = _ctx(user, f)
    by_id = {p.id: p for p in projects}
    scores = review_score_map(list(by_id))
    q = db.session.query(ProjectReview).filter(ProjectReview.project_id.in_(list(by_id) or [-1]))
    if f.get("week"):
        q = q.filter(ProjectReview.week_no == f["week"])
    if f.get("status"):
        q = q.filter(ProjectReview.status == f["status"])
    rows = []
    for r in q.order_by(ProjectReview.project_id, ProjectReview.week_no):
        p = by_id[r.project_id]
        got, mx = scores.get(r.id, (None, None))
        mentor = db.session.get(Mentor, r.mentor_id) if r.mentor_id else None
        rows.append({
            "batch": p.batch.code, "project": p.title, "students": ", ".join(m.student.user.name for m in p.members), "week": f"Week {r.week_no}",
            "mentor": mentor.user.name if mentor else ", ".join(x.user.name for x in mentors[p.id]) or "—",
            "status": ev.STATUS_LABEL[r.status], "due_date": r.due_date.isoformat() if r.due_date else None,
            "overdue": "Yes" if r.status != "submitted" and r.due_date and r.due_date < date.today() else "No",
            "submitted_at": r.submitted_at.date().isoformat() if r.submitted_at else None,
            "obtained": got, "max": mx, "percentage": _pct(got, mx) if mx else None})
    return _cols(("batch", "Batch"), ("project", "Project"), ("students", "Student(s)"), ("week", "Week"), ("mentor", "Mentor"), ("status", "Status"),
                 ("due_date", "Due"), ("overdue", "Overdue"), ("submitted_at", "Submitted"), ("obtained", "Marks obtained"), ("max", "Max marks"),
                 ("percentage", "Percentage")), rows


def report_completion(user, f):
    projects, metrics, mentors = _ctx(user, f)
    rows = []
    for p in sorted(projects, key=lambda p: (p.batch.code, p.id)):
        m = metrics[p.id]
        done = p.completed_at.date() if p.completed_at else None
        late = (done - p.target_end_date).days if done and p.target_end_date else None
        rows.append({
            "batch": p.batch.code, "project": p.title, "students": ", ".join(x.student.user.name for x in p.members),
            "mentor": ", ".join(x.user.name for x in mentors[p.id]) or "—", "stage": lifecycle.LABELS[p.stage],
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "target_end_date": p.target_end_date.isoformat() if p.target_end_date else None,
            "completed_on": done.isoformat() if done else None,
            "on_time": "—" if late is None else ("Yes" if late <= 0 else f"No ({late}d late)"),
            "progress": m["progress"], "reviews": f"{m['reviews_submitted']}/4", "final_signed_off": "Yes" if p.final_signed_off_by else "No",
            "score_pct": m["score_pct"], "delayed": "Yes" if m["is_delayed"] else "No"})
    return _cols(("batch", "Batch"), ("project", "Project"), ("students", "Student(s)"), ("mentor", "Mentor"), ("stage", "Stage"),
                 ("start_date", "Started"), ("target_end_date", "Target end"), ("completed_on", "Completed on"), ("on_time", "On time"),
                 ("progress", "Progress %"), ("reviews", "Reviews"), ("final_signed_off", "Final sign-off"), ("score_pct", "Overall score %"),
                 ("delayed", "Delayed")), rows


# type -> (title, builder, roles allowed, filters it honours)
REPORTS = {
    "ou": ("OU-wise report", report_ou, {"admin"}, ["ou_id"]),
    "domain": ("Domain-wise report", report_domain, {"admin", "domain_lead"}, ["domain_id"]),
    "batch": ("Batch-wise report", report_batch, {"admin", "domain_lead", "mentor"}, ["ou_id", "domain_id", "batch_id"]),
    "student": ("Student-wise report", report_student, {"admin", "domain_lead", "mentor"}, ["ou_id", "domain_id", "batch_id", "stage", "mentor_id"]),
    "mentor": ("Mentor-wise report", report_mentor, {"admin", "domain_lead"}, ["ou_id", "domain_id", "batch_id"]),
    "weekly-evaluations": ("Weekly evaluation report", report_weekly, {"admin", "domain_lead", "mentor"}, ["ou_id", "domain_id", "batch_id", "mentor_id", "week", "status"]),
    "project-completion": ("Project completion report", report_completion, {"admin", "domain_lead", "mentor"}, ["ou_id", "domain_id", "batch_id", "mentor_id", "stage"]),
}


def available_reports(user):
    return [{"type": k, "title": t, "filters": fl} for k, (t, _, roles, fl) in REPORTS.items() if user.role_name in roles]


def build(user, report_type, filters):
    if report_type not in REPORTS:
        raise AppError("Unknown report", 404)
    title, builder, roles, allowed = REPORTS[report_type]
    if user.role_name not in roles:
        raise Forbidden("You do not have access to this report")
    clean = {k: v for k, v in filters.items() if k in allowed and v not in (None, "")}
    columns, rows = builder(user, clean)
    return {"type": report_type, "title": title, "columns": columns, "rows": rows,
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "filters": clean}


# ------------------------------------------------------------------ exports
def to_csv(report):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([c["label"] for c in report["columns"]])
    for r in report["rows"][:MAX_EXPORT_ROWS]:
        w.writerow([_safe("" if r.get(c["key"]) is None else r.get(c["key"])) for c in report["columns"]])
    return ("﻿" + out.getvalue()).encode("utf-8")


def to_xlsx(report):
    wb = Workbook()
    ws = wb.active
    ws.title = report["title"][:31]
    ws.append([c["label"] for c in report["columns"]])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in report["rows"][:MAX_EXPORT_ROWS]:
        ws.append([_safe(r.get(c["key"])) for c in report["columns"]])
    for i, c in enumerate(report["columns"], 1):
        width = max([len(str(c["label"]))] + [len(str(r.get(c["key"]) or "")) for r in report["rows"][:200]])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(width + 2, 10), 50)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------ detailed, per-batch report (admin / domain lead)
DETAILED_SHEETS = ("students", "weekly", "criteria")


def batch_detailed(user, batch):
    """Everything about one batch: summary, every student's project status, every weekly score with remarks,
    and the per-criterion marks. Unpublished (draft) scores are never exported; only submitted evaluations carry marks.
    """
    projects = load_projects(user, {"batch_id": batch.id})
    metrics = project_metrics(projects)
    mentors = mentors_by_project(projects)
    by_student = {m.student_id: p for p in projects for m in p.members}
    ids = [p.id for p in projects]
    reviews = defaultdict(dict)
    if ids:
        q = (db.session.query(ProjectReview).options(selectinload(ProjectReview.criteria).joinedload(EvaluationCriterion.score))
             .filter(ProjectReview.project_id.in_(ids)).order_by(ProjectReview.week_no))
        for r in q:
            reviews[r.project_id][r.week_no] = r
    personal = {(r.review_id, r.student_id): r.remarks for r in db.session.query(ReviewStudentRemark).filter(
        ReviewStudentRemark.review_id.in_([r.id for rs in reviews.values() for r in rs.values()] or [-1]))}
    github = {g.project_id: g.url for g in db.session.query(ProjectGithubRepository).filter(ProjectGithubRepository.project_id.in_(ids or [-1]))}
    from app.models import User
    mentor_names = {}

    def mentor_name(mid):
        if mid not in mentor_names:
            m = db.session.get(Mentor, mid) if mid else None
            mentor_names[mid] = m.user.name if m else None
        return mentor_names[mid]

    students = db.session.query(Student).filter_by(batch_id=batch.id).order_by(Student.registration_no).all()
    student_rows, weekly_rows, criteria_rows = [], [], []
    for s in students:
        p = by_student.get(s.id)
        base = {"student": s.user.name, "registration_no": s.registration_no, "email": s.user.email, "phone": s.user.phone or ""}
        if not p:
            student_rows.append({**base, "project": "Not allocated", "team": "—", "mentor": "—", "stage": "—", "delayed": "—"})
            continue
        m = metrics[p.id]
        row = {**base, "project": p.title, "problem_statement": f"{p.problem_statement.ps_code} – {p.problem_statement.title}",
               "team": f"Team of {len(p.members)}" if len(p.members) > 1 else "Individual",
               "mentor": ", ".join(x.user.name for x in mentors[p.id]) or "—", "stage": lifecycle.LABELS[p.stage],
               "progress": m["progress"], "srs": SRS_LABELS[srs_status_of(p.stage)], "github": github.get(p.id) or "—",
               "tasks": f"{m['tasks']['completed']}/{m['tasks']['total']}", "overall_score_pct": m["score_pct"],
               "final_signed_off": "Yes" if p.final_signed_off_by else "No", "final_remarks": p.final_remarks if p.final_signed_off_by else "",
               "delayed": "Yes" if m["is_delayed"] else "No", "delay_reasons": "; ".join(m["delay_reasons"])}
        for week in range(1, 5):
            r = reviews[p.id].get(week)
            published = bool(r and r.status == "submitted")
            got = sum(float(c.score.marks_obtained) for c in r.criteria if c.score) if published else None
            mx = sum(float(c.max_marks) for c in r.criteria) if published else None
            pct = _pct(got, mx) if published and mx else None
            row[f"w{week}_pct"] = pct
            weekly_rows.append({
                **{k: base[k] for k in ("student", "registration_no")}, "project": p.title, "week": f"Week {week}",
                "status": ev.STATUS_LABEL[r.status] if r else "—", "due_date": r.due_date.isoformat() if r and r.due_date else None,
                "submitted_on": r.submitted_at.date().isoformat() if published and r.submitted_at else None,
                "mentor": mentor_name(r.mentor_id) if published else None, "marks": got, "max_marks": mx, "percentage": pct,
                "overall_feedback": r.remarks if published else None, "strengths": r.strengths if published else None,
                "improvements": r.improvements if published else None, "recommendations": r.recommendations if published else None,
                "student_remarks": personal.get((r.id, s.id)) if published else None})
            if published:
                for c in r.criteria:
                    criteria_rows.append({"student": s.user.name, "registration_no": s.registration_no, "project": p.title, "week": f"Week {week}",
                                          "criterion": c.name, "max_marks": float(c.max_marks),
                                          "marks_obtained": float(c.score.marks_obtained) if c.score else None,
                                          "criterion_remarks": c.score.remarks if c.score else None})
        student_rows.append(row)

    agg = _agg(projects, metrics)
    mentor_list = sorted({x.user.name for ms in mentors.values() for x in ms})
    summary = [
        ("Batch code", batch.code), ("Batch name", batch.name), ("OU", batch.ou.name), ("Domain", batch.domain.name if batch.domain else "—"),
        ("Status", batch.status), ("Start date", batch.start_date.isoformat() if batch.start_date else "—"),
        ("End date", batch.end_date.isoformat() if batch.end_date else "—"), ("Students", len(students)),
        ("Students with a project", sum(1 for s in students if s.id in by_student)), ("Projects", agg["projects"]),
        ("Completed", agg["completed"]), ("In progress", agg["in_progress"]), ("Delayed", agg["delayed"]),
        ("Average progress %", agg["avg_progress"]), ("Average evaluation %", agg["avg_score_pct"]), ("Mentors", ", ".join(mentor_list) or "—"),
        ("Generated on", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")), ("Generated by", user.name),
    ]
    sheets = {
        "students": (_cols(("student", "Student"), ("registration_no", "Reg. no"), ("email", "Email"), ("phone", "Phone"), ("project", "Project"),
                           ("problem_statement", "Problem statement"), ("team", "Team"), ("mentor", "Mentor"), ("stage", "Stage"),
                           ("progress", "Progress %"), ("srs", "SRS"), ("github", "GitHub"), ("tasks", "Tasks done"),
                           ("w1_pct", "Week 1 %"), ("w2_pct", "Week 2 %"), ("w3_pct", "Week 3 %"), ("w4_pct", "Week 4 %"),
                           ("overall_score_pct", "Overall score %"), ("final_signed_off", "Final sign-off"), ("final_remarks", "Final remarks"),
                           ("delayed", "Delayed"), ("delay_reasons", "Delay reasons")), student_rows),
        "weekly": (_cols(("student", "Student"), ("registration_no", "Reg. no"), ("project", "Project"), ("week", "Week"), ("status", "Status"),
                         ("due_date", "Due"), ("submitted_on", "Submitted"), ("mentor", "Scored by"), ("marks", "Marks"), ("max_marks", "Out of"),
                         ("percentage", "%"), ("overall_feedback", "Overall feedback"), ("strengths", "Strengths"),
                         ("improvements", "Areas for improvement"), ("recommendations", "Recommendations"),
                         ("student_remarks", "Remarks for this student")), weekly_rows),
        "criteria": (_cols(("student", "Student"), ("registration_no", "Reg. no"), ("project", "Project"), ("week", "Week"), ("criterion", "Criterion"),
                           ("max_marks", "Max marks"), ("marks_obtained", "Marks obtained"), ("criterion_remarks", "Remarks")), criteria_rows),
    }
    return {"batch": {"id": batch.id, "code": batch.code, "name": batch.name}, "summary": summary, "sheets": sheets}


def detailed_to_xlsx(report):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Batch detailed report", ""])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    for k, v in report["summary"]:
        ws.append([k, _safe(v)])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 60
    titles = {"students": "Students", "weekly": "Weekly scores", "criteria": "Criteria scores"}
    for key in DETAILED_SHEETS:
        columns, rows = report["sheets"][key]
        sh = wb.create_sheet(titles[key])
        sh.append([c["label"] for c in columns])
        for cell in sh[1]:
            cell.font = Font(bold=True)
        for r in rows:
            sh.append([_safe(r.get(c["key"])) for c in columns])
        for i, c in enumerate(columns, 1):
            width = max([len(str(c["label"]))] + [len(str(r.get(c["key"]) or "")) for r in rows[:200]])
            sh.column_dimensions[sh.cell(row=1, column=i).column_letter].width = min(max(width + 2, 10), 60)
        sh.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def detailed_sheet_csv(report, sheet):
    columns, rows = report["sheets"][sheet]
    return to_csv({"columns": columns, "rows": rows})
