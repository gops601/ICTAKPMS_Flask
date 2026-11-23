import io
from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook

from app.extensions import db
from app.models import (AuditLog, Batch, BatchMentor, Domain, DomainLead, EvaluationCriterion, EvaluationScore, Mentor,
                        OrganisationalUnit, ProblemStatement, Project, ProjectGithubRepository, ProjectReview, ProjectStudent,
                        ScrumBoard, ScrumTask, Student)
from app.models.base import utcnow
from app.services.metrics_service import project_metrics
from app.services.project_service import compute_progress, delay_reasons

TODAY = date.today()


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


def add_review(project, week, status="pending", pct=None, remarks=None, due=None):
    r = ProjectReview(project_id=project.id, week_no=week, status=status, due_date=due or project.start_date + timedelta(weeks=week), remarks=remarks)
    db.session.add(r)
    db.session.flush()
    if pct is not None:
        c = EvaluationCriterion(review_id=r.id, name="Overall", max_marks=100, display_order=0)
        db.session.add(c)
        db.session.flush()
        db.session.add(EvaluationScore(criterion_id=c.id, marks_obtained=pct))
        r.submitted_at = utcnow()
    return r


@pytest.fixture()
def world(make_user, login):
    """
    AIML/B1 (lead la, mentor m1): p1 implementation (reviews 80%,50%, github, 1/2 tasks, one overdue task) → delayed
                                   p2 srs_submitted (fresh), p3 completed (4 reviews @90%, signed off), s4 has no project
    IOT/B2  (lead lb, mentor m3):  p5 srs_preparation started 3 weeks ago → delayed
    """
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id), DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    b1 = Batch(code="B1", name="Batch One", ou_id=ou.id, domain_id=domain("AIML").id)
    b2 = Batch(code="B2", name="Batch Two", ou_id=ou.id, domain_id=domain("IOT").id)
    db.session.add_all([b1, b2])
    m1u, m3u = make_user("mentor", "m1@x.com", name="Mia One"), make_user("mentor", "m3@x.com", name="Max Three")
    m1, m3 = Mentor(user_id=m1u.id), Mentor(user_id=m3u.id)
    db.session.add_all([m1, m3])
    db.session.flush()
    db.session.add_all([BatchMentor(batch_id=b1.id, mentor_id=m1.id), BatchMentor(batch_id=b2.id, mentor_id=m3.id)])
    users = {n: make_user("student", f"{n}@x.com", name=f"Student {n}") for n in ("s1", "s2", "s3", "s4", "s5")}
    db.session.flush()
    studs = {n: Student(user_id=u.id, batch_id=(b2.id if n == "s5" else b1.id), registration_no=n.upper()) for n, u in users.items()}
    db.session.add_all(studs.values())
    ps = ProblemStatement(ps_code="PS1", title="T", domain_id=domain("AIML").id, description="d")
    ps2 = ProblemStatement(ps_code="PS2", title="U", domain_id=domain("AIML").id, description="d")
    ps5 = ProblemStatement(ps_code="PS5", title="V", domain_id=domain("IOT").id, description="d")
    db.session.add_all([ps, ps2, ps5])
    db.session.flush()

    def project(name, batch, student, stage, start, psx=ps, **kw):
        p = Project(batch_id=batch.id, problem_statement_id=psx.id, title=name, stage=stage, start_date=start, target_end_date=start + timedelta(weeks=4), **kw)
        db.session.add(p)
        db.session.flush()
        db.session.add(ProjectStudent(project_id=p.id, student_id=studs[student].id))
        db.session.add(ScrumBoard(project_id=p.id))
        return p

    p1 = project("Alpha", b1, "s1", "implementation", TODAY)
    p2 = project("Beta", b1, "s2", "srs_submitted", TODAY)
    p3 = project("Gamma", b1, "s3", "completed", TODAY - timedelta(days=40), final_signed_off_by=m1u.id, completed_at=utcnow())
    p5 = project("Epsilon", b2, "s5", "srs_preparation", TODAY - timedelta(weeks=3), psx=ps5)
    add_review(p1, 1, "submitted", 80, "Good start"); add_review(p1, 2, "submitted", 50, "Needs work")
    add_review(p1, 3); add_review(p1, 4)
    for w in range(1, 5):
        add_review(p2, w)
        add_review(p3, w, "submitted", 90, f"Done {w}")
        add_review(p5, w)
    db.session.add(ProjectGithubRepository(project_id=p1.id, url="https://github.com/o/alpha"))
    board = db.session.query(ScrumBoard).filter_by(project_id=p1.id).one()
    db.session.add_all([ScrumTask(board_id=board.id, title="done", status="completed"),
                        ScrumTask(board_id=board.id, title="late", status="todo", due_date=TODAY - timedelta(days=2))])
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "la", "lb", "m1", "m3", "s1", "s4")}
    return dict(H=H, p1=p1, p2=p2, p3=p3, p5=p5, studs=studs, users=users)


def dash(client, world, who):
    r = client.get("/api/dashboard", headers=world["H"][who])
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


# --------------------------------------------------------------- shared engine
def test_bulk_metrics_match_single_project_helpers(world):
    projects = db.session.query(Project).all()
    bulk = project_metrics(projects)
    for p in projects:
        assert bulk[p.id]["progress"] == compute_progress(p)
        assert bulk[p.id]["delay_reasons"] == delay_reasons(p)
    assert bulk[world["p1"].id]["progress"] == 57.5                       # SRS 20 + GitHub 5 + Scrum 12.5 + reviews 20
    assert bulk[world["p3"].id]["progress"] == 20 + 40 + 10               # SRS + 4 reviews + final (no scrum/github)
    assert bulk[world["p1"].id]["score_pct"] == 65.0                      # (80+50)/200
    assert bulk[world["p1"].id]["delay_reasons"] == ["1 Scrum task(s) overdue"]
    assert "SRS not approved after week 1" in bulk[world["p5"].id]["delay_reasons"]
    assert bulk[world["p3"].id]["is_delayed"] is False and bulk[world["p2"].id]["is_delayed"] is False


def test_bulk_metrics_use_a_constant_number_of_queries(world, app):
    from sqlalchemy import event
    projects = db.session.query(Project).all()
    count = {"n": 0}
    engine = db.engine

    def tick(*a, **k):
        count["n"] += 1
    event.listen(engine, "before_cursor_execute", tick)
    try:
        project_metrics(projects)
    finally:
        event.remove(engine, "before_cursor_execute", tick)
    assert count["n"] <= 5                                                # reviews, scores, github, tasks, weights


# ------------------------------------------------------------------ admin
def test_admin_dashboard_counts_and_charts(client, world):
    d = dash(client, world, "admin")
    c = d["counts"]
    assert (c["students"], c["mentors"], c["batches"], c["domains"], c["ous"]) == (5, 2, 2, 6, 4)
    assert c["problem_statements"] == 3 and c["projects_total"] == 4
    assert c["in_progress"] == 3 and c["awaiting_srs_approval"] == 1 and c["completed"] == 1 and c["delayed"] == 2
    assert c["pending_reviews"] == 1                                       # only p5 has reviews that are due
    assert d["status_split"] == {"completed": 1, "delayed": 2, "ongoing": 1}
    stages = {x["stage"]: x["count"] for x in d["stage_distribution"]}
    assert stages["implementation"] == 1 and stages["completed"] == 1 and stages["allocated"] == 0 and len(d["stage_distribution"]) == 9
    assert d["review_completion"] == {"submitted": 6, "total": 16, "rate_pct": 37.5, "by_week": d["review_completion"]["by_week"]}
    wk = {w["week"]: w for w in d["review_completion"]["by_week"]}
    assert wk["Week 1"] == {"week": "Week 1", "submitted": 2, "in_progress": 0, "pending": 2}
    avg = {a["week"]: a["average"] for a in d["average_scores"]}
    assert avg == {"Week 1": 85.0, "Week 2": 70.0, "Week 3": 90.0, "Week 4": 90.0}
    dist = {x["name"]: x["projects"] for x in d["domain_distribution"]}
    assert dist == {"AI & ML": 3, "IoT": 1}
    assert d["ou_distribution"][0]["projects"] == 4 and d["ou_distribution"][0]["completed"] == 1
    prog = {b["batch"]: b["average_progress"] for b in d["batch_progress"]}
    assert set(prog) == {"B1", "B2"}
    work = {m["mentor"]: m["projects"] for m in d["mentor_workload"]}
    assert work == {"Mia One": 3, "Max Three": 1}
    part = {x["ou"]: (x["with_project"], x["without_project"]) for x in d["student_participation"]}
    assert part["Retail OU"] == (4, 1)                                     # s4 has no project


def test_dashboards_use_live_data(client, world):
    before = dash(client, world, "admin")["counts"]["completed"]
    world["p1"].stage = "completed"
    db.session.commit()
    assert dash(client, world, "admin")["counts"]["completed"] == before + 1


# --------------------------------------------------------------- domain lead
def test_lead_dashboard_is_scoped_to_their_domain(client, world):
    d = dash(client, world, "la")
    c = d["counts"]
    assert c == {"batches": 1, "students": 4, "mentors": 1, "problem_statements": 2, "projects_allocated": 3, "srs_pending_approval": 1,
                 "under_implementation": 1, "reviews_pending": c["reviews_pending"], "completed": 1, "delayed": 1,
                 "date_requests_pending": 0}
    assert [s["label"] for s in d["srs_status"]] == ["Not submitted", "Submitted", "Under review", "Changes requested", "Approved"]
    assert {s["status"]: s["count"] for s in d["srs_status"]} == {"not_submitted": 0, "submitted": 1, "under_review": 0, "changes_requested": 0, "approved": 2}
    assert d["scrum"] == {"total": 2, "completed": 1, "overdue": 1, "in_flight": 1, "completion_pct": 50.0}
    mentors = {m["mentor"]: m for m in d["mentor_review_completion"]}
    assert set(mentors) == {"Mia One"} and mentors["Mia One"]["submitted"] == 6
    assert {x["batch"] for x in d["batch_progress"]} == {"B1"}
    assert all(x["student"] != "Student s5" for x in d["student_progress"])
    assert d["student_progress"][0]["progress"] <= d["student_progress"][-1]["progress"]    # lowest progress first
    other = dash(client, world, "lb")["counts"]
    assert (other["batches"], other["projects_allocated"], other["delayed"], other["mentors"]) == (1, 1, 1, 1)


# --------------------------------------------------------------------- mentor
def test_mentor_dashboard(client, world):
    d = dash(client, world, "m1")
    c = d["counts"]
    assert c["assigned_batches"] == 1 and c["students"] == 3 and c["active_projects"] == 2
    assert c["srs_pending_approval"] == 1 and c["srs_approved"] == 2 and c["reviews_completed"] == 6
    assert c["reviews_pending"] == 3                                       # p1 weeks 3-4 + p2 week 1
    assert c["needs_attention"] == 2 and c["nearing_completion"] == 0
    assert [q["title"] for q in d["srs_queue"]] == ["Beta"]
    reasons = {a["title"]: a["reasons"] for a in d["students_requiring_attention"]}
    assert reasons["Beta"] == ["SRS waiting for your review"] and "overdue" in reasons["Alpha"][0]
    assert {r["week_no"] for r in d["review_queue"]} == {1, 3, 4} and len(d["review_queue"]) == 3
    assert d["scrum"]["total"] == 2
    # a mentor of another batch sees none of this
    other = dash(client, world, "m3")["counts"]
    assert other["students"] == 1 and other["reviews_completed"] == 0


def test_mentor_nearing_completion_threshold(client, world):
    p = world["p1"]
    db.session.add(ScrumTask(board_id=db.session.query(ScrumBoard).filter_by(project_id=p.id).one().id, title="x", status="completed"))
    for t in db.session.query(ScrumTask).filter_by(title="late"):
        t.status = "completed"
    for r in db.session.query(ProjectReview).filter_by(project_id=p.id):
        r.status = "submitted"
    db.session.commit()
    d = dash(client, world, "m1")
    assert d["counts"]["nearing_completion"] == 1 and d["nearing_completion"][0]["title"] == "Alpha" and d["nearing_completion"][0]["progress"] >= 75


# -------------------------------------------------------------------- student
def test_student_dashboard(client, world):
    d = dash(client, world, "s1")
    assert d["project"]["title"] == "Alpha" and d["project"]["progress"] == 57.5 and d["project"]["is_delayed"] is True
    assert d["domain"] == "AI & ML" and d["batch"]["code"] == "B1" and d["mentors"] == ["Mia One"]
    assert d["srs_status"] == "approved" and d["github_url"] == "https://github.com/o/alpha"
    assert [(r["label"], r["status"]) for r in d["reviews"]] == [("Week 1", "submitted"), ("Week 2", "submitted"), ("Week 3", "pending"), ("Week 4", "pending")]
    # students never receive marks or percentages, only the mentor's remarks
    assert all({"percentage", "obtained", "max"}.isdisjoint(r) for r in d["reviews"]) and "overall_score_pct" not in d
    assert d["latest_mentor_feedback"]["remarks"] == "Needs work" and d["latest_mentor_feedback"]["week_no"] == 2
    assert d["scrum"] == {"total": 2, "completed": 1, "overdue": 1}
    assert d["timeline"] == []                                             # fixture created no transitions


def test_student_without_project_and_visibility_rules(client, world):
    d = dash(client, world, "s4")
    assert d["project"] is None and d["batch"]["code"] == "B1"
    # unpublished (draft) review content never reaches the student dashboard
    r = db.session.query(ProjectReview).filter_by(project_id=world["p1"].id, week_no=3).one()
    r.status, r.remarks = "draft", "SECRET DRAFT"
    db.session.commit()
    body = client.get("/api/dashboard", headers=world["H"]["s1"]).get_data(as_text=True)
    assert "SECRET DRAFT" not in body


def test_dashboard_requires_authentication(client, world):
    assert client.get("/api/dashboard").status_code == 401


# --------------------------------------------------------------------- reports
def rep(client, world, who, kind, qs=""):
    return client.get(f"/api/reports/{kind}{qs}", headers=world["H"][who])


def rows(resp):
    return resp.get_json()["data"]["rows"]


def test_report_catalogue_by_role(client, world):
    kinds = lambda who: {r["type"] for r in client.get("/api/reports", headers=world["H"][who]).get_json()["data"]}  # noqa: E731
    assert kinds("admin") == {"ou", "domain", "batch", "student", "mentor", "weekly-evaluations", "project-completion"}
    assert kinds("la") == kinds("admin") - {"ou"}
    assert kinds("m1") == {"batch", "student", "weekly-evaluations", "project-completion"}
    assert kinds("s1") == set()
    assert rep(client, world, "s1", "student").status_code == 403
    assert rep(client, world, "la", "ou").status_code == 403
    assert rep(client, world, "m1", "mentor").status_code == 403
    assert rep(client, world, "admin", "nope").status_code == 404
    assert client.get("/api/reports/student").status_code == 401


def test_ou_and_domain_reports(client, world):
    ou = {r["ou"]: r for r in rows(rep(client, world, "admin", "ou"))}
    assert ou["Retail OU"]["batches"] == 2 and ou["Retail OU"]["students"] == 5 and ou["Retail OU"]["projects"] == 4
    assert ou["Retail OU"]["completed"] == 1 and ou["Retail OU"]["delayed"] == 2 and ou["Academic OU"]["projects"] == 0
    dom = {r["domain"]: r for r in rows(rep(client, world, "admin", "domain"))}
    assert dom["AI & ML"]["projects"] == 3 and dom["AI & ML"]["students"] == 4 and dom["IoT"]["projects"] == 1
    assert dom["AI & ML"]["avg_score_pct"] is not None
    assert [r["domain"] for r in rows(rep(client, world, "la", "domain"))] == ["AI & ML"]          # scoped lead
    assert [r["domain"] for r in rows(rep(client, world, "admin", "domain", "?domain_id=" + str(domain("IOT").id)))] == ["IoT"]


def test_batch_report_scoping_and_values(client, world):
    admin_rows = {r["code"]: r for r in rows(rep(client, world, "admin", "batch"))}
    assert set(admin_rows) == {"B1", "B2"}
    b1 = admin_rows["B1"]
    assert (b1["students"], b1["projects"], b1["completed"], b1["delayed"], b1["in_progress"]) == (4, 3, 1, 1, 2)
    assert b1["avg_progress"] == 42.5                                      # (57.5 + 0 + 70) / 3
    assert [r["code"] for r in rows(rep(client, world, "la", "batch"))] == ["B1"]
    assert [r["code"] for r in rows(rep(client, world, "m1", "batch"))] == ["B1"]
    assert [r["code"] for r in rows(rep(client, world, "m3", "batch"))] == ["B2"]
    assert [r["code"] for r in rows(rep(client, world, "admin", "batch", "?batch_id=" + str(db.session.query(Batch).filter_by(code="B2").one().id)))] == ["B2"]


def test_student_report_includes_unallocated_and_respects_scope_and_filters(client, world):
    by_reg = {r["registration_no"]: r for r in rows(rep(client, world, "admin", "student"))}
    assert set(by_reg) == {"S1", "S2", "S3", "S4", "S5"}
    s1, s4 = by_reg["S1"], by_reg["S4"]
    assert (s1["project"], s1["stage"], s1["progress"], s1["github"], s1["reviews_submitted"], s1["score_pct"], s1["delayed"]) == \
        ("Alpha", "Implementation", 57.5, "Yes", "2/4", 65.0, "Yes")
    assert s1["tasks_done_pct"] == 50.0 and s1["mentor"] == "Mia One" and s1["srs"] == "Approved"
    assert s4["project"] == "Not allocated" and s4["progress"] is None
    assert {r["registration_no"] for r in rows(rep(client, world, "la", "student"))} == {"S1", "S2", "S3", "S4"}
    assert {r["registration_no"] for r in rows(rep(client, world, "m3", "student"))} == {"S5"}
    assert {r["registration_no"] for r in rows(rep(client, world, "admin", "student", "?stage=completed"))} == {"S3"}
    mid = db.session.get(Mentor, 1).id                                    # Mia One (batch B1)
    assert {r["registration_no"] for r in rows(rep(client, world, "admin", "student", f"?mentor_id={mid}"))} == {"S1", "S2", "S3"}


def test_mentor_report(client, world):
    ms = {r["mentor"]: r for r in rows(rep(client, world, "admin", "mentor"))}
    m = ms["Mia One"]
    assert (m["projects"], m["batches"], m["completed"], m["reviews_submitted"], m["reviews_pending"]) == (3, 1, 1, 6, 3)
    assert m["review_completion_pct"] == 66.7 and m["delayed"] == 1 and m["avg_score_given_pct"] is not None
    assert ms["Max Three"]["reviews_overdue"] == 2                    # due dates: 2 weeks ago, 1 week ago, today (not yet overdue), future
    assert set(r["mentor"] for r in rows(rep(client, world, "la", "mentor"))) == {"Mia One"}


def test_weekly_evaluation_report(client, world):
    allrows = rows(rep(client, world, "admin", "weekly-evaluations?per_page=200"))
    assert len(allrows) == 16
    assert len(rows(rep(client, world, "admin", "weekly-evaluations", "?week=1"))) == 4
    sub = rows(rep(client, world, "admin", "weekly-evaluations", "?status=submitted&per_page=200"))
    assert len(sub) == 6 and all(r["percentage"] is not None and r["status"] == "Submitted" for r in sub)
    a_w1 = next(r for r in sub if r["project"] == "Alpha" and r["week"] == "Week 1")
    assert (a_w1["obtained"], a_w1["max"], a_w1["percentage"]) == (80.0, 100.0, 80.0)
    overdue = [r for r in allrows if r["overdue"] == "Yes"]
    assert len(overdue) == 2 and all(r["project"] == "Epsilon" for r in overdue)
    assert len(rows(rep(client, world, "m1", "weekly-evaluations", "?per_page=200"))) == 12            # only their projects
    assert len(rows(rep(client, world, "m3", "weekly-evaluations", "?per_page=200"))) == 4


def test_project_completion_report(client, world):
    world["p3"].target_end_date = TODAY - timedelta(days=12)
    db.session.commit()
    by = {r["project"]: r for r in rows(rep(client, world, "admin", "project-completion"))}
    g = by["Gamma"]
    assert g["stage"] == "Completed" and g["final_signed_off"] == "Yes" and g["reviews"] == "4/4" and g["on_time"] == "No (12d late)"
    assert by["Alpha"]["completed_on"] is None and by["Alpha"]["on_time"] == "—" and by["Alpha"]["delayed"] == "Yes"
    assert {r["project"] for r in rows(rep(client, world, "la", "project-completion"))} == {"Alpha", "Beta", "Gamma"}


def test_report_pagination(client, world):
    r = rep(client, world, "admin", "weekly-evaluations", "?per_page=5&page=2").get_json()
    assert len(r["data"]["rows"]) == 5 and r["meta"] == {"page": 2, "per_page": 5, "total": 16, "pages": 4}
    assert r["data"]["columns"][0] == {"key": "batch", "label": "Batch"}


# --------------------------------------------------------------------- exports
def test_csv_export(client, world):
    r = rep(client, world, "admin", "student", "?format=csv")
    assert r.status_code == 200 and r.mimetype == "text/csv" and 'attachment; filename="student_' in r.headers["Content-Disposition"]
    text = r.data.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("Student,Reg. no,Email,Batch") and len(lines) == 6            # header + 5 students
    assert "Not allocated" in text and r.data.startswith(b"\xef\xbb\xbf")                    # BOM so Excel reads UTF-8
    assert db.session.query(AuditLog).filter_by(action="report.export").count() == 1


def test_xlsx_export_is_a_valid_workbook(client, world):
    r = rep(client, world, "admin", "batch", "?format=xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype
    ws = load_workbook(io.BytesIO(r.data)).active
    header = [c.value for c in ws[1]]
    assert header[:3] == ["Batch code", "Batch", "OU"] and ws.max_row == 3
    assert ws["A2"].value == "B1" and ws.freeze_panes == "A2"


def test_exports_are_scoped_and_unfiltered_by_pagination(client, world):
    csv_rows = rep(client, world, "la", "weekly-evaluations", "?format=csv&per_page=1").data.decode("utf-8-sig").strip().splitlines()
    assert len(csv_rows) == 13                                                                 # header + all 12 rows of the lead's domain
    assert rep(client, world, "s1", "student", "?format=csv").status_code == 403


def test_exports_neutralise_formula_injection(client, world):
    world["users"]["s4"].name = "=HYPERLINK(\"http://evil\",\"x\")"
    db.session.commit()
    csv_text = rep(client, world, "admin", "student", "?format=csv").data.decode("utf-8-sig")
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text
    ws = load_workbook(io.BytesIO(rep(client, world, "admin", "student", "?format=xlsx").data)).active
    cells = [c.value for row in ws.iter_rows(min_row=2) for c in row if isinstance(c.value, str)]
    assert any(v.startswith("'=HYPERLINK") for v in cells) and not any(v.startswith("=") for v in cells)
