"""Single source of truth for project progress, delay and score metrics.

`project_metrics()` computes everything for MANY projects with a handful of grouped queries (no per-project
round trips), and the single-project helpers in project_service delegate to it. Dashboards, reports and the
project page therefore can never disagree about a project's progress or whether it is delayed.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import (EvaluationCriterion, EvaluationScore, ProjectGithubRepository, ProjectReview, ScrumBoard,
                        ScrumTask, SystemSetting)
from app.services import lifecycle

PROJECT_WEEKS = 4
DEFAULT_WEIGHTS = {"srs": 20, "github": 5, "scrum": 25, "reviews": 40, "final": 10}
_APPROVED = lifecycle.ORDER["srs_approved"]


def progress_weights():
    """Configurable (system_settings.progress_weights), normalised to 100."""
    row = db.session.get(SystemSetting, "progress_weights")
    weights = {**DEFAULT_WEIGHTS, **(row.value if row and isinstance(row.value, dict) else {})}
    total = sum(weights.values()) or 1
    return {k: v * 100 / total for k, v in weights.items()}


def project_metrics(projects, today=None):
    """{project_id: metrics dict} for the given Project objects."""
    today = today or date.today()
    ids = [p.id for p in projects]
    if not ids:
        return {}
    w = progress_weights()

    reviews = {i: [] for i in ids}
    for pid, week, status, due in (db.session.query(ProjectReview.project_id, ProjectReview.week_no, ProjectReview.status,
                                                    ProjectReview.due_date).filter(ProjectReview.project_id.in_(ids))):
        reviews[pid].append((week, status, due))

    # score totals of SUBMITTED reviews only
    scores = {i: [0.0, 0.0] for i in ids}  # [obtained, max]
    q = (db.session.query(ProjectReview.project_id, db.func.sum(EvaluationCriterion.max_marks),
                          db.func.sum(EvaluationScore.marks_obtained))
         .join(EvaluationCriterion, EvaluationCriterion.review_id == ProjectReview.id)
         .outerjoin(EvaluationScore, EvaluationScore.criterion_id == EvaluationCriterion.id)
         .filter(ProjectReview.project_id.in_(ids), ProjectReview.status == "submitted")
         .group_by(ProjectReview.project_id))
    for pid, mx, got in q:
        scores[pid] = [float(got or 0), float(mx or 0)]

    github = {r[0] for r in db.session.query(ProjectGithubRepository.project_id).filter(ProjectGithubRepository.project_id.in_(ids))}

    tasks = {i: {"total": 0, "completed": 0, "overdue": 0} for i in ids}
    q = (db.session.query(ScrumBoard.project_id, ScrumTask.status, ScrumTask.due_date)
         .join(ScrumTask, ScrumTask.board_id == ScrumBoard.id)
         .filter(ScrumBoard.project_id.in_(ids), ScrumTask.is_archived.is_(False)))
    for pid, status, due in q:
        t = tasks[pid]
        t["total"] += 1
        if status == "completed":
            t["completed"] += 1
        elif due and due < today:
            t["overdue"] += 1

    out = {}
    for p in projects:
        order = lifecycle.ORDER[p.stage]
        rv = reviews[p.id]
        submitted = sum(1 for _, s, _ in rv if s == "submitted")
        overdue_reviews = sum(1 for _, s, d in rv if s != "submitted" and d and d < today)
        due_reviews = sum(1 for _, s, d in rv if s != "submitted" and d and d <= today)
        t = tasks[p.id]
        done = 0.0
        if order >= _APPROVED:
            done += w["srs"]
        if p.id in github:
            done += w["github"]
        if t["total"]:
            done += w["scrum"] * t["completed"] / t["total"]
        done += w["reviews"] * submitted / PROJECT_WEEKS
        if p.stage == "completed" or p.final_signed_off_by:
            done += w["final"]

        reasons = []
        if p.stage != "completed":
            if overdue_reviews:
                reasons.append(f"{overdue_reviews} weekly review(s) overdue")
            if p.start_date and p.start_date + timedelta(weeks=1) < today and order < _APPROVED:
                reasons.append("SRS not approved after week 1")
            if t["overdue"]:
                reasons.append(f"{t['overdue']} Scrum task(s) overdue")

        got, mx = scores[p.id]
        out[p.id] = {
            "progress": round(min(done, 100), 1), "delay_reasons": reasons, "is_delayed": bool(reasons),
            "reviews_submitted": submitted, "reviews_overdue": overdue_reviews, "reviews_due": due_reviews,
            "reviews": {week: status for week, status, _ in rv},
            "score_obtained": got, "score_max": mx, "score_pct": round(got * 100 / mx, 2) if mx else None,
            "has_github": p.id in github, "tasks": t,
        }
    return out


def review_score_map(project_ids):
    """{review_id: (obtained, max)} for submitted reviews of the given projects."""
    if not project_ids:
        return {}
    q = (db.session.query(ProjectReview.id, db.func.sum(EvaluationCriterion.max_marks), db.func.sum(EvaluationScore.marks_obtained))
         .join(EvaluationCriterion, EvaluationCriterion.review_id == ProjectReview.id)
         .outerjoin(EvaluationScore, EvaluationScore.criterion_id == EvaluationCriterion.id)
         .filter(ProjectReview.project_id.in_(project_ids), ProjectReview.status == "submitted")
         .group_by(ProjectReview.id))
    return {rid: (float(got or 0), float(mx or 0)) for rid, mx, got in q}
