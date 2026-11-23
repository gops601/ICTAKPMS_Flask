"""Role-specific dashboard payloads. Everything is computed from live data (no placeholders)."""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, Mentor, OrganisationalUnit, ProblemStatement, Project, ProjectReview,
                        ProjectStudent, Student, SrsSubmission)
from app.permissions.scope import lead_domain_ids, mentor_batch_ids, mentor_profile, scoped_batches, scoped_projects, student_profile
from app.services import evaluation_service as ev
from app.services import lifecycle
from app.services.metrics_service import project_metrics, review_score_map

IN_PROGRESS = ("srs_preparation", "srs_submitted", "srs_under_review", "srs_changes_requested", "srs_approved", "implementation", "final_evaluation")
AWAITING_SRS = ("srs_submitted", "srs_under_review")
SRS_STATUS_ORDER = ["not_submitted", "submitted", "under_review", "changes_requested", "approved"]
SRS_LABELS = {"not_submitted": "Not submitted", "submitted": "Submitted", "under_review": "Under review",
              "changes_requested": "Changes requested", "approved": "Approved"}
TOP_N = 12


# ------------------------------------------------------------------ data loading
def load_projects(user, filters=None):
    """Scoped projects with the relations dashboards/reports need preloaded."""
    q = scoped_projects(user)
    f = filters or {}
    if f.get("batch_id"):
        q = q.where(Project.batch_id == f["batch_id"])
    if f.get("domain_id") or f.get("ou_id"):
        sub = db.select(Batch.id)
        if f.get("domain_id"):
            sub = sub.where(Batch.domain_id == f["domain_id"])
        if f.get("ou_id"):
            sub = sub.where(Batch.ou_id == f["ou_id"])
        q = q.where(Project.batch_id.in_(sub))
    if f.get("stage"):
        q = q.where(Project.stage == f["stage"])
    if f.get("mentor_id"):
        mid = f["mentor_id"]
        via_batch = db.select(BatchMentor.batch_id).where(BatchMentor.mentor_id == mid, BatchMentor.is_active.is_(True))
        q = q.where(db.or_(Project.mentor_id == mid, db.and_(Project.mentor_id.is_(None), Project.batch_id.in_(via_batch))))
    q = q.options(joinedload(Project.batch).joinedload(Batch.ou), joinedload(Project.batch).joinedload(Batch.domain),
                  joinedload(Project.problem_statement),
                  selectinload(Project.members).joinedload(ProjectStudent.student).joinedload(Student.user))
    return list(db.session.scalars(q).unique())


def mentors_by_project(projects):
    """{project_id: [Mentor]} honouring per-project overrides, else the batch's active mentors."""
    batch_ids = {p.batch_id for p in projects}
    by_batch = defaultdict(list)
    if batch_ids:
        for bm, m in (db.session.query(BatchMentor, Mentor).join(Mentor, Mentor.id == BatchMentor.mentor_id)
                      .filter(BatchMentor.batch_id.in_(batch_ids), BatchMentor.is_active.is_(True))):
            by_batch[bm.batch_id].append(m)
    override_ids = {p.mentor_id for p in projects if p.mentor_id}
    overrides = {m.id: m for m in db.session.query(Mentor).filter(Mentor.id.in_(override_ids or {-1}))} if override_ids else {}
    return {p.id: ([overrides[p.mentor_id]] if p.mentor_id in overrides else (by_batch[p.batch_id] if not p.mentor_id else []))
            for p in projects}


def srs_status_of(stage):
    order = lifecycle.ORDER[stage]
    if order >= lifecycle.ORDER["srs_approved"]:
        return "approved"
    return {"srs_submitted": "submitted", "srs_under_review": "under_review", "srs_changes_requested": "changes_requested"}.get(stage, "not_submitted")


def evaluable_pending(project, metrics):
    """Weeks that can be evaluated right now and are not yet submitted."""
    return [w for w, status in metrics["reviews"].items() if status != "submitted" and ev.week_gate(project, w) is None]


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else 0.0


def _status_split(projects, metrics):
    completed = sum(1 for p in projects if p.stage == "completed")
    delayed = sum(1 for p in projects if metrics[p.id]["is_delayed"])
    return {"completed": completed, "delayed": delayed, "ongoing": len(projects) - completed - delayed}


def _stage_distribution(projects):
    c = Counter(p.stage for p in projects)
    return [{"stage": s, "label": lifecycle.LABELS[s], "count": c.get(s, 0)} for s in lifecycle.STAGES]


def _srs_distribution(projects):
    c = Counter(srs_status_of(p.stage) for p in projects)
    return [{"status": s, "label": SRS_LABELS[s], "count": c.get(s, 0)} for s in SRS_STATUS_ORDER]


def _scrum_totals(projects, metrics):
    total = sum(metrics[p.id]["tasks"]["total"] for p in projects)
    done = sum(metrics[p.id]["tasks"]["completed"] for p in projects)
    over = sum(metrics[p.id]["tasks"]["overdue"] for p in projects)
    return {"total": total, "completed": done, "overdue": over, "in_flight": total - done,
            "completion_pct": round(done * 100 / total, 1) if total else 0.0}


def _weekly_status(projects):
    ids = [p.id for p in projects]
    rows = Counter()
    if ids:
        for week, status, n in (db.session.query(ProjectReview.week_no, ProjectReview.status, db.func.count(ProjectReview.id))
                                .filter(ProjectReview.project_id.in_(ids)).group_by(ProjectReview.week_no, ProjectReview.status)):
            rows[(week, status)] = n
    return [{"week": f"Week {w}", "submitted": rows[(w, "submitted")], "in_progress": rows[(w, "draft")] + rows[(w, "reopened")],
             "pending": rows[(w, "pending")]} for w in range(1, 5)]


def _avg_scores_by_week(projects):
    ids = [p.id for p in projects]
    scores = review_score_map(ids)
    per_week = defaultdict(list)
    if scores:
        for rid, week in db.session.query(ProjectReview.id, ProjectReview.week_no).filter(ProjectReview.id.in_(list(scores))):
            got, mx = scores[rid]
            if mx:
                per_week[week].append(got * 100 / mx)
    return [{"week": f"Week {w}", "average": _avg(per_week[w]), "reviews": len(per_week[w])} for w in range(1, 5)]


def _batch_progress(projects, metrics):
    groups = defaultdict(list)
    for p in projects:
        groups[p.batch].append(metrics[p.id]["progress"])
    rows = [{"batch": b.code, "average_progress": _avg(v), "projects": len(v)} for b, v in groups.items()]
    return sorted(rows, key=lambda r: r["batch"])[:TOP_N * 2]


def _student_progress(projects, metrics, limit=TOP_N):
    rows = []
    for p in projects:
        for m in p.members:
            rows.append({"student": m.student.user.name, "registration_no": m.student.registration_no, "project_id": p.id,
                         "stage": lifecycle.LABELS[p.stage],
                         "progress": metrics[p.id]["progress"], "is_delayed": metrics[p.id]["is_delayed"]})
    return sorted(rows, key=lambda r: (r["progress"], r["student"]))[:limit]


def _mentor_review_completion(projects, metrics, mentors):
    agg = defaultdict(lambda: {"submitted": 0, "pending": 0, "projects": 0})
    for p in projects:
        for m in mentors[p.id]:
            a = agg[m.user.name]
            a["projects"] += 1
            a["submitted"] += metrics[p.id]["reviews_submitted"]
            a["pending"] += len(evaluable_pending(p, metrics[p.id]))
    rows = [{"mentor": name, **a, "completion_pct": round(a["submitted"] * 100 / (a["submitted"] + a["pending"]), 1) if a["submitted"] + a["pending"] else 0.0}
            for name, a in agg.items()]
    return sorted(rows, key=lambda r: r["mentor"])[:TOP_N]


def _pending_date_requests(project_ids):
    if not project_ids:
        return 0
    from app.models import ReviewDateRequest
    return (db.session.query(ReviewDateRequest).join(ProjectReview, ProjectReview.id == ReviewDateRequest.review_id)
            .filter(ReviewDateRequest.status == "pending", ProjectReview.project_id.in_(project_ids)).count())


# --------------------------------------------------------------------- admin
def _filtered_batch(filters):
    bid = (filters or {}).get("batch_id")
    return db.session.get(Batch, bid) if bid else None


def admin_dashboard(user, filters=None):
    projects = load_projects(user, filters)
    metrics = project_metrics(projects)
    mentors = mentors_by_project(projects)
    batch = _filtered_batch(filters)
    if batch:   # one batch: every institution-level count narrows to it
        batch_mentors = {r[0] for r in db.session.query(BatchMentor.mentor_id).filter_by(batch_id=batch.id, is_active=True)}
        batch_mentors |= {m.id for ms in mentors.values() for m in ms}
        base = {"ous": 1, "domains": 1 if batch.domain_id else 0, "batches": 1,
                "students": db.session.query(Student).filter_by(batch_id=batch.id).count(), "mentors": len(batch_mentors),
                "problem_statements": db.session.query(ProblemStatement).filter_by(domain_id=batch.domain_id).count() if batch.domain_id else 0}
    else:
        base = {"ous": db.session.query(OrganisationalUnit).count(), "domains": db.session.query(Domain).count(),
                "batches": db.session.query(Batch).count(), "students": db.session.query(Student).count(),
                "mentors": db.session.query(Mentor).count(), "problem_statements": db.session.query(ProblemStatement).count()}
    counts = {
        **base,
        "projects_total": len(projects),
        "in_progress": sum(1 for p in projects if p.stage in IN_PROGRESS),
        "awaiting_srs_approval": sum(1 for p in projects if p.stage in AWAITING_SRS),
        "pending_reviews": sum(1 for p in projects if metrics[p.id]["reviews_due"] and p.stage != "completed"),
        "completed": sum(1 for p in projects if p.stage == "completed"),
        "delayed": sum(1 for p in projects if metrics[p.id]["is_delayed"]),
    }
    by_ou, by_domain = defaultdict(Counter), defaultdict(Counter)
    for p in projects:
        for key, bucket in ((p.batch.ou.name, by_ou), (p.batch.domain.name if p.batch.domain else "Unassigned", by_domain)):
            bucket[key]["projects"] += 1
            bucket[key]["completed"] += p.stage == "completed"
    load = Counter()
    for p in projects:
        for m in mentors[p.id]:
            load[m.user.name] += 1
    participation = []
    for ou in db.session.query(OrganisationalUnit).order_by(OrganisationalUnit.name):
        if batch and ou.id != batch.ou_id:
            continue
        students_q = db.session.query(Student).join(Batch, Batch.id == Student.batch_id).filter(Batch.ou_id == ou.id)
        placed_q = (db.session.query(ProjectStudent.student_id).join(Student, Student.id == ProjectStudent.student_id)
                    .join(Batch, Batch.id == Student.batch_id).filter(Batch.ou_id == ou.id))
        if batch:
            students_q, placed_q = students_q.filter(Batch.id == batch.id), placed_q.filter(Batch.id == batch.id)
        total, placed = students_q.count(), placed_q.distinct().count()
        participation.append({"ou": ou.name, "with_project": placed, "without_project": total - placed})
    ids = [p.id for p in projects]
    total_reviews = db.session.query(ProjectReview).filter(ProjectReview.project_id.in_(ids or [-1])).count()
    done_reviews = sum(metrics[i]["reviews_submitted"] for i in ids)
    return {"role": "admin", "counts": counts, "status_split": _status_split(projects, metrics),
            "stage_distribution": _stage_distribution(projects),
            "ou_distribution": [{"name": k, "projects": v["projects"], "completed": v["completed"]} for k, v in sorted(by_ou.items())],
            "domain_distribution": [{"name": k, "projects": v["projects"], "completed": v["completed"]} for k, v in sorted(by_domain.items())],
            "batch_progress": _batch_progress(projects, metrics), "student_participation": participation,
            "mentor_workload": [{"mentor": k, "projects": v} for k, v in load.most_common(TOP_N)],
            "review_completion": {"submitted": done_reviews, "total": total_reviews,
                                  "rate_pct": round(done_reviews * 100 / total_reviews, 1) if total_reviews else 0.0,
                                  "by_week": _weekly_status(projects)},
            "average_scores": _avg_scores_by_week(projects)}


# ---------------------------------------------------------------------- lead
def lead_dashboard(user, filters=None):
    domain_ids = lead_domain_ids(user)
    projects = load_projects(user, filters)
    metrics = project_metrics(projects)
    mentors = mentors_by_project(projects)
    bq = scoped_batches(user)
    if (filters or {}).get("batch_id"):
        bq = bq.where(Batch.id == filters["batch_id"])
    batches = list(db.session.scalars(bq))
    batch_ids = [b.id for b in batches]
    mentor_ids = {m.id for ms in mentors.values() for m in ms}
    if batch_ids:
        mentor_ids |= {r[0] for r in db.session.query(BatchMentor.mentor_id).filter(BatchMentor.batch_id.in_(batch_ids), BatchMentor.is_active.is_(True))}
    counts = {
        "batches": len(batches),
        "students": db.session.query(Student).filter(Student.batch_id.in_(batch_ids or [-1])).count(),
        "mentors": len(mentor_ids),
        "problem_statements": db.session.query(ProblemStatement).filter(ProblemStatement.domain_id.in_(domain_ids or {-1})).count(),
        "projects_allocated": len(projects),
        "srs_pending_approval": sum(1 for p in projects if p.stage in AWAITING_SRS),
        "under_implementation": sum(1 for p in projects if p.stage in ("implementation", "final_evaluation")),
        "reviews_pending": sum(len(evaluable_pending(p, metrics[p.id])) for p in projects if metrics[p.id]["reviews_due"]),
        "completed": sum(1 for p in projects if p.stage == "completed"),
        "delayed": sum(1 for p in projects if metrics[p.id]["is_delayed"]),
        "date_requests_pending": _pending_date_requests([p.id for p in projects]),
    }
    return {"role": "domain_lead", "counts": counts, "status_split": _status_split(projects, metrics),
            "stage_distribution": _stage_distribution(projects), "batch_progress": _batch_progress(projects, metrics),
            "mentor_review_completion": _mentor_review_completion(projects, metrics, mentors),
            "srs_status": _srs_distribution(projects), "weekly_evaluation_status": _weekly_status(projects),
            "scrum": _scrum_totals(projects, metrics), "average_scores": _avg_scores_by_week(projects),
            "student_progress": _student_progress(projects, metrics)}


# -------------------------------------------------------------------- mentor
def mentor_dashboard(user, filters=None):
    projects = load_projects(user, filters)
    metrics = project_metrics(projects)
    mentor = mentor_profile(user)
    # a mentor's own scope: projects where they are the effective mentor
    mentors = mentors_by_project(projects)
    mine = [p for p in projects if mentor and any(m.id == mentor.id for m in mentors[p.id])]
    student_ids = {m.student_id for p in mine for m in p.members}
    active = [p for p in mine if p.stage != "completed"]
    pending = {p.id: evaluable_pending(p, metrics[p.id]) for p in mine}
    attention = []
    for p in active:
        m = metrics[p.id]
        reasons = list(m["delay_reasons"])
        if p.stage in AWAITING_SRS:
            reasons.append("SRS waiting for your review")
        if reasons:
            attention.append({"project_id": p.id, "title": p.title, "students": [x.student.user.name for x in p.members],
                              "progress": m["progress"], "reasons": reasons})
    srs_queue = []
    for p in sorted((p for p in mine if p.stage in AWAITING_SRS), key=lambda p: p.updated_at)[:5]:
        sub = db.session.query(SrsSubmission).filter_by(project_id=p.id).order_by(SrsSubmission.version.desc()).first()
        srs_queue.append({"project_id": p.id, "title": p.title, "students": [x.student.user.name for x in p.members],
                          "version": sub.version if sub else None})
    review_queue = []
    ids = [p.id for p in mine if pending[p.id]]
    if ids:
        for r in (db.session.query(ProjectReview).filter(ProjectReview.project_id.in_(ids), ProjectReview.status != "submitted")
                  .order_by(ProjectReview.due_date, ProjectReview.id)):
            p = next(x for x in mine if x.id == r.project_id)
            if ev.week_gate(p, r.week_no) is None:
                review_queue.append({"review_id": r.id, "week_no": r.week_no, "due_date": r.due_date.isoformat() if r.due_date else None,
                                     "is_overdue": bool(r.due_date and r.due_date < date.today()), "status": r.status,
                                     "project": p.title, "students": [x.student.user.name for x in p.members]})
    counts = {
        "assigned_batches": 1 if (filters or {}).get("batch_id") else len(mentor_batch_ids(user)), "students": len(student_ids), "active_projects": len(active),
        "srs_pending_approval": sum(1 for p in mine if p.stage in AWAITING_SRS),
        "srs_approved": sum(1 for p in mine if lifecycle.ORDER[p.stage] >= lifecycle.ORDER["srs_approved"]),
        "reviews_pending": sum(len(v) for v in pending.values()),
        "reviews_completed": sum(metrics[p.id]["reviews_submitted"] for p in mine),
        "needs_attention": len(attention),
        "nearing_completion": sum(1 for p in active if metrics[p.id]["progress"] >= 75),
    }
    nearing = [{"project_id": p.id, "title": p.title, "progress": metrics[p.id]["progress"]}
               for p in sorted(active, key=lambda p: -metrics[p.id]["progress"]) if metrics[p.id]["progress"] >= 75][:5]
    return {"role": "mentor", "counts": counts, "srs_queue": srs_queue, "review_queue": review_queue[:8],
            "students_requiring_attention": attention[:8], "nearing_completion": nearing,
            "stage_distribution": _stage_distribution(mine), "scrum": _scrum_totals(mine, metrics),
            "student_progress": _student_progress(mine, metrics), "weekly_evaluation_status": _weekly_status(mine)}


# ------------------------------------------------------------------- student
def student_dashboard(user, filters=None):
    s = student_profile(user)
    projects = load_projects(user)
    if not projects:
        return {"role": "student", "project": None, "batch": {"code": s.batch.code, "name": s.batch.name} if s else None}
    p = projects[0]
    m = project_metrics([p])[p.id]
    mentors = mentors_by_project([p])[p.id]
    reviews = db.session.query(ProjectReview).filter_by(project_id=p.id).order_by(ProjectReview.week_no).all()
    week_rows, latest = [], None
    for r in reviews:
        row = {"week_no": r.week_no, "label": f"Week {r.week_no}", "due_date": r.due_date.isoformat() if r.due_date else None,
               "status": "submitted" if r.status == "submitted" else "pending"}
        if r.status == "submitted":  # students are shown remarks only, never marks or percentages
            if latest is None or r.week_no > latest["week_no"]:
                latest = {"week_no": r.week_no, "remarks": r.remarks, "mentor": None}
        week_rows.append(row)
    transitions = []
    from app.models import ProjectLifecycleTransition
    for t in db.session.query(ProjectLifecycleTransition).filter_by(project_id=p.id).order_by(ProjectLifecycleTransition.id):
        transitions.append({"stage": t.to_stage, "label": lifecycle.LABELS[t.to_stage], "at": t.created_at.isoformat(), "is_reopen": t.is_reopen})
    srs_sub = db.session.query(SrsSubmission).filter_by(project_id=p.id).order_by(SrsSubmission.version.desc()).first()
    srs_remark = None
    if srs_sub and srs_sub.history:
        h = sorted(srs_sub.history, key=lambda x: x.id)[-1]
        srs_remark = {"decision": h.decision, "remarks": h.remarks}
    repo = None
    from app.models import ProjectGithubRepository
    gh = db.session.query(ProjectGithubRepository).filter_by(project_id=p.id).first()
    if gh:
        repo = gh.url
    return {
        "role": "student",
        "project": {"id": p.id, "title": p.title, "stage": p.stage, "stage_label": lifecycle.LABELS[p.stage],
                    "progress": m["progress"], "is_delayed": m["is_delayed"], "delay_reasons": m["delay_reasons"],
                    "start_date": p.start_date.isoformat() if p.start_date else None,
                    "target_end_date": p.target_end_date.isoformat() if p.target_end_date else None},
        "problem_statement": {"id": p.problem_statement.id, "ps_code": p.problem_statement.ps_code, "title": p.problem_statement.title},
        "domain": p.batch.domain.name if p.batch.domain else None,
        "batch": {"code": p.batch.code, "name": p.batch.name}, "mentors": [x.user.name for x in mentors],
        "srs_status": srs_status_of(p.stage), "srs_status_label": SRS_LABELS[srs_status_of(p.stage)], "latest_srs_feedback": srs_remark,
        "reviews": week_rows, "latest_mentor_feedback": latest, "scrum": m["tasks"], "github_url": repo,
        "timeline": transitions,
    }


BUILDERS = {"admin": admin_dashboard, "domain_lead": lead_dashboard, "mentor": mentor_dashboard, "student": student_dashboard}
