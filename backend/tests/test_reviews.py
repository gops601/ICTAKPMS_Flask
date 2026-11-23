import pytest

from app.extensions import db
from app.models import (AuditLog, Batch, BatchMentor, Domain, DomainLead, EvaluationCriterion, EvaluationRevision,
                        EvaluationScore, EvaluationTemplate, Mentor, Notification, OrganisationalUnit, ProblemStatement,
                        Project, ProjectReview, ProjectStudent, Student)
from app.services import evaluation_service as ev
from app.services.project_service import compute_progress


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id), DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    m1u, m2u = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com")
    m1, m2 = Mentor(user_id=m1u.id), Mentor(user_id=m2u.id)
    db.session.add_all([m1, m2])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    su = {n: make_user("student", f"{n}@x.com") for n in ("s1", "s2", "s3")}
    db.session.flush()
    studs = {n: Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper()) for n, u in su.items()}
    db.session.add_all(studs.values())
    ps = ProblemStatement(ps_code="PS1", title="T", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.flush()
    projects = {}
    for n, members, stage in (("main", ["s1"], "implementation"), ("early", ["s2"], "srs_preparation"), ("fresh", ["s3"], "allocated")):
        p = Project(batch_id=batch.id, problem_statement_id=ps.id, title=f"Project {n}", stage=stage)
        db.session.add(p)
        db.session.flush()
        for m in members:
            db.session.add(ProjectStudent(project_id=p.id, student_id=studs[m].id))
        from datetime import date, timedelta
        for w in range(1, 5):
            db.session.add(ProjectReview(project_id=p.id, week_no=w, due_date=date.today() + timedelta(weeks=w)))
        projects[n] = p
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "la", "lb", "m1", "m2", "s1", "s2", "s3")}
    return dict(H=H, main=projects["main"], early=projects["early"], fresh=projects["fresh"], m1u=m1u, s1u=su["s1"], m1=m1)


def rid(project, week):
    return db.session.query(ProjectReview).filter_by(project_id=project.id, week_no=week).one().id


CRIT = [{"name": "Problem Understanding", "max_marks": 20, "marks_obtained": 15},
        {"name": "Requirement Analysis", "max_marks": 20, "marks_obtained": 18},
        {"name": "SRS Quality", "max_marks": 30, "marks_obtained": 24},
        {"name": "Technical Feasibility", "max_marks": 30, "marks_obtained": 27}]          # 84 / 100


def put(client, world, who, review_id, **payload):
    return client.put(f"/api/reviews/{review_id}", headers=world["H"][who], json=payload)


def submit(client, world, who, review_id, **payload):
    return client.post(f"/api/reviews/{review_id}/submit", headers=world["H"][who], json=payload)


def full(criteria=None, remarks="Good work"):
    return {"criteria": criteria or CRIT, "remarks": remarks, "strengths": "Clear scope", "improvements": "More tests",
            "recommendations": "Read IEEE 830"}


def submit_all(client, world, project=None):
    project = project or world["main"]
    for w in range(1, 5):
        r = submit(client, world, "m1", rid(project, w), **full())
        assert r.status_code == 200, r.get_json()


# --------------------------------------------------------------- dynamic criteria
def test_nothing_is_preconfigured(client, world):
    d = client.get(f"/api/reviews/{rid(world['main'], 1)}", headers=world["H"]["m1"]).get_json()["data"]
    assert d["criteria"] == [] and d["status"] == "pending" and d["summary"]["total_max"] == 0.0
    assert d["permissions"]["can_edit"] is True


def test_mentor_defines_criteria_and_scores_with_automatic_totals(client, world):
    r = put(client, world, "m1", rid(world["main"], 1), **full())
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "draft"
    assert d["summary"] == {"total_obtained": 84.0, "total_max": 100.0, "percentage": 84.0, "criteria_count": 4, "scored_count": 4}
    assert [c["name"] for c in d["criteria"]] == [c["name"] for c in CRIT]


def test_criteria_can_be_added_edited_removed_and_reordered_before_submission(client, world):
    rv = rid(world["main"], 2)
    d = put(client, world, "m1", rv, criteria=[{"name": "Design", "max_marks": 40, "marks_obtained": 30}, {"name": "Code", "max_marks": 60}]).get_json()["data"]
    design, code = d["criteria"]
    assert d["summary"]["scored_count"] == 1 and d["summary"]["percentage"] == 30.0           # unscored criteria count as 0
    d = put(client, world, "m1", rv, version=d["version"], criteria=[
        {"id": code["id"], "name": "Code Quality", "max_marks": 50, "marks_obtained": 45},    # renamed, new max, scored
        {"name": "Testing", "max_marks": 10, "marks_obtained": 5},                            # added
        # 'Design' removed
    ]).get_json()["data"]
    assert [c["name"] for c in d["criteria"]] == ["Code Quality", "Testing"]
    assert d["summary"]["total_obtained"] == 50.0 and d["summary"]["total_max"] == 60.0 and d["summary"]["percentage"] == 83.33
    assert db.session.query(EvaluationCriterion).filter_by(review_id=rv).count() == 2
    assert db.session.query(EvaluationScore).count() == 2                                     # removed criterion's score is gone
    # a score can be cleared again
    d = put(client, world, "m1", rv, criteria=[{"id": c["id"], "name": c["name"], "max_marks": c["max_marks"]} for c in d["criteria"]]).get_json()["data"]
    assert d["summary"]["scored_count"] == 0 and d["summary"]["percentage"] == 0.0


def test_each_review_has_independent_criteria(client, world):
    put(client, world, "m1", rid(world["main"], 1), **full())
    put(client, world, "m1", rid(world["main"], 2), criteria=[{"name": "Only one", "max_marks": 10}])
    w1 = client.get(f"/api/reviews/{rid(world['main'], 1)}", headers=world["H"]["m1"]).get_json()["data"]
    w2 = client.get(f"/api/reviews/{rid(world['main'], 2)}", headers=world["H"]["m1"]).get_json()["data"]
    assert len(w1["criteria"]) == 4 and len(w2["criteria"]) == 1


@pytest.mark.parametrize("criteria,field", [
    ([{"name": "", "max_marks": 10}], "criteria.0.name"),
    ([{"name": "A", "max_marks": 0}], "criteria.0.max_marks"),
    ([{"name": "A", "max_marks": -5}], "criteria.0.max_marks"),
    ([{"name": "A", "max_marks": 1001}], "criteria.0.max_marks"),
    ([{"name": "A", "max_marks": "abc"}], "criteria.0.max_marks"),
    ([{"name": "A", "max_marks": "NaN"}], "criteria.0.max_marks"),
    ([{"name": "A", "max_marks": 10, "marks_obtained": 11}], "criteria.0.marks_obtained"),
    ([{"name": "A", "max_marks": 10, "marks_obtained": -1}], "criteria.0.marks_obtained"),
    ([{"name": "A", "max_marks": 10, "marks_obtained": "x"}], "criteria.0.marks_obtained"),
    ([{"name": "A", "max_marks": 10}, {"name": " a ", "max_marks": 5}], "criteria.1.name"),
    ([{"name": "x" * 151, "max_marks": 10}], "criteria.0.name"),
])
def test_criteria_validation(client, world, criteria, field):
    r = put(client, world, "m1", rid(world["main"], 1), criteria=criteria)
    assert r.status_code == 422 and field in r.get_json()["errors"]
    assert db.session.query(EvaluationCriterion).count() == 0


def test_too_many_criteria_and_foreign_criterion_ids(client, world):
    assert put(client, world, "m1", rid(world["main"], 1), criteria=[{"name": f"C{i}", "max_marks": 1} for i in range(21)]).status_code == 422
    put(client, world, "m1", rid(world["main"], 2), criteria=[{"name": "Mine", "max_marks": 5}])
    foreign = db.session.query(EvaluationCriterion).one().id
    r = put(client, world, "m1", rid(world["main"], 1), criteria=[{"id": foreign, "name": "Stolen", "max_marks": 5}])
    assert r.status_code == 422 and "does not belong" in r.get_json()["message"]


def test_decimal_marks_rounded_to_two_places(client, world):
    d = put(client, world, "m1", rid(world["main"], 1), criteria=[{"name": "A", "max_marks": "10.5", "marks_obtained": "7.255"}]).get_json()["data"]
    assert d["criteria"][0]["marks_obtained"] == 7.26 and d["summary"]["percentage"] == 69.14


def test_feedback_fields_and_review_date_saved(client, world):
    d = put(client, world, "m1", rid(world["main"], 1), remarks="R", strengths="S", improvements="I", recommendations="Rec", review_date="2026-03-09").get_json()["data"]
    assert (d["remarks"], d["strengths"], d["improvements"], d["recommendations"], d["review_date"]) == ("R", "S", "I", "Rec", "2026-03-09")
    assert put(client, world, "m1", rid(world["main"], 1), review_date="garbage").status_code == 422
    assert put(client, world, "m1", rid(world["main"], 1), strengths="x" * 5001).status_code == 422


# ----------------------------------------------------------------------- submit
def test_submit_calculates_and_publishes_to_student(client, world):
    rv = rid(world["main"], 1)
    put(client, world, "m1", rv, **full())
    assert client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]["visible"] is False   # draft hidden
    r = submit(client, world, "m1", rv)
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "submitted" and d["summary"]["percentage"] == 84.0
    assert d["submitted_at"] and d["review_date"] and d["mentor"] == "Mentor"
    s = client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]
    assert s["visible"] is True and s["summary"] is None and s["strengths"] == "Clear scope" and s["improvements"] == "More tests"
    assert s["permissions"]["can_edit"] is False and s["permissions"]["can_reopen"] is False
    n = db.session.query(Notification).filter_by(user_id=world["s1u"].id, type="review_completed").one()
    assert "remarks" in n.message and "84" not in n.message and "%" not in n.message   # no score in the student notification


def test_submit_in_one_call_with_payload(client, world):
    r = submit(client, world, "m1", rid(world["main"], 1), **full())
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "submitted"


@pytest.mark.parametrize("payload,msg", [
    ({"remarks": "ok"}, "at least one evaluation criterion"),
    ({"criteria": [{"name": "A", "max_marks": 10, "marks_obtained": 5}, {"name": "B", "max_marks": 10}], "remarks": "ok"}, "Score every criterion"),
    ({"criteria": [{"name": "A", "max_marks": 10, "marks_obtained": 5}], "remarks": "  "}, "Overall feedback is required"),
])
def test_submit_requirements(client, world, payload, msg):
    r = submit(client, world, "m1", rid(world["main"], 1), **payload)
    assert r.status_code == 422 and msg in r.get_json()["message"]
    assert db.session.get(ProjectReview, rid(world["main"], 1)).status != "submitted"


def test_submitted_review_is_locked_for_edits_and_resubmission(client, world):
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full())
    assert put(client, world, "m1", rv, remarks="changed").status_code == 409
    assert put(client, world, "m1", rv, criteria=[{"name": "New", "max_marks": 5}]).status_code == 409
    assert submit(client, world, "m1", rv, **full()).status_code == 409
    assert db.session.query(EvaluationCriterion).filter_by(review_id=rv).count() == 4


def test_optimistic_version_conflict(client, world):
    rv = rid(world["main"], 1)
    v1 = put(client, world, "m1", rv, **full()).get_json()["data"]["version"]
    assert put(client, world, "m1", rv, remarks="a", version=v1).status_code == 200
    r = put(client, world, "m1", rv, remarks="b", version=v1)
    assert r.status_code == 409 and "changed elsewhere" in r.get_json()["message"]


# --------------------------------------------------------------------- permissions
@pytest.mark.parametrize("who,code", [("s1", 403), ("s2", 403), ("la", 403), ("admin", 403), ("m2", 404), ("lb", 403)])
def test_only_assigned_mentor_can_evaluate(client, world, who, code):
    assert put(client, world, who, rid(world["main"], 1), **full()).status_code == code
    assert submit(client, world, who, rid(world["main"], 1), **full()).status_code == code
    assert db.session.get(ProjectReview, rid(world["main"], 1)).status == "pending"


def test_unassigned_mentor_cannot_see_review(client, world):
    assert client.get(f"/api/reviews/{rid(world['main'], 1)}", headers=world["H"]["m2"]).status_code == 404
    assert client.get(f"/api/reviews/projects/{world['main'].id}", headers=world["H"]["m2"]).status_code == 404




def test_project_override_mentor_takes_over_evaluation(client, world):
    m2 = db.session.query(Mentor).filter(Mentor.id != world["m1"].id).one()
    world["main"].mentor_id = m2.id
    db.session.commit()
    assert put(client, world, "m1", rid(world["main"], 1), **full()).status_code == 404      # batch mentor displaced by the override
    assert put(client, world, "m2", rid(world["main"], 1), **full()).status_code == 200      # override mentor allowed (has scope via the project)


# ----------------------------------------------------------------------- stage gate
def test_week_gating_by_project_stage(client, world):
    early, fresh = world["early"], world["fresh"]
    assert put(client, world, "m1", rid(early, 1), **full()).status_code == 200              # SRS phase: week 1 fine
    for w in (2, 3, 4):
        r = put(client, world, "m1", rid(early, w), **full())
        assert r.status_code == 409 and "implementation has started" in r.get_json()["message"]
    for w in (1, 2):
        assert put(client, world, "m1", rid(fresh, w), **full()).status_code == 409           # not started at all
    assert "SRS preparation" in put(client, world, "m1", rid(fresh, 1), **full()).get_json()["message"]
    world["main"].stage = "completed"
    db.session.commit()
    r = put(client, world, "m1", rid(world["main"], 1), **full())
    assert r.status_code == 409 and "completed" in r.get_json()["message"]


def test_permissions_object_explains_why_not(client, world):
    d = client.get(f"/api/reviews/{rid(world['early'], 3)}", headers=world["H"]["m1"]).get_json()["data"]
    assert d["permissions"]["can_edit"] is False and "implementation" in d["permissions"]["reason"]


# -------------------------------------------------------------------- audited reopen
def test_reopen_is_controlled_snapshotted_and_audited(client, world):
    rv = rid(world["main"], 1)
    reopen = lambda who, reason="Scores were mis-keyed": client.post(f"/api/reviews/{rv}/reopen", headers=world["H"][who], json={"reason": reason})  # noqa: E731
    assert reopen("m1").status_code == 409                                                    # not submitted yet
    submit(client, world, "m1", rv, **full())
    for who, code in (("s1", 403), ("m2", 404), ("lb", 404)):          # students cannot; an unassigned mentor / other domain lead sees nothing
        assert reopen(who).status_code == code, who
    assert reopen("m1", "no").status_code == 422 and reopen("m1", "").status_code == 422
    assert db.session.get(ProjectReview, rv).status == "submitted"
    db.session.query(Notification).delete()
    db.session.commit()
    r = reopen("m1")
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "reopened" and d["permissions"]["can_edit"] is True
    # hidden from the student while under revision, who is told
    s = client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]
    assert s["visible"] is False and s["status_label"] == "Under revision"
    assert db.session.query(Notification).filter_by(user_id=world["s1u"].id, type="review_reopened").count() == 1
    # previous state is preserved verbatim
    rev = db.session.query(EvaluationRevision).one()
    assert rev.reason == "Scores were mis-keyed" and rev.snapshot["summary"]["percentage"] == 84.0 and len(rev.snapshot["criteria"]) == 4
    assert db.session.query(AuditLog).filter_by(action="review.reopen", entity_id=rv).count() == 1
    # now editable again (criteria included), and resubmission re-publishes
    crit = d["criteria"]
    crit[0]["marks_obtained"] = 20
    assert put(client, world, "m1", rv, criteria=crit).status_code == 200
    r = submit(client, world, "m1", rv)
    assert r.get_json()["data"]["summary"]["total_obtained"] == 89.0
    assert client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]["summary"] is None
    revs = client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["la"]).get_json()["data"]
    assert len(revs) == 1 and revs[0]["changed_by"] == "Mentor" and revs[0]["snapshot"]["summary"]["total_obtained"] == 84.0
    assert client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["s1"]).status_code == 403
    assert client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["m2"]).status_code == 404


def test_each_reopen_adds_a_revision_and_admin_may_reopen(client, world):
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full())
    assert client.post(f"/api/reviews/{rv}/reopen", headers=world["H"]["admin"], json={"reason": "Admin correction"}).status_code == 200
    submit(client, world, "m1", rv)
    client.post(f"/api/reviews/{rv}/reopen", headers=world["H"]["m1"], json={"reason": "Second correction"})
    assert [r["reason"] for r in client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["m1"]).get_json()["data"]] == ["Second correction", "Admin correction"]


def test_cannot_reopen_review_of_completed_project(client, world):
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full())
    world["main"].stage = "completed"
    db.session.commit()
    r = client.post(f"/api/reviews/{rv}/reopen", headers=world["H"]["m1"], json={"reason": "Too late now"})
    assert r.status_code == 409 and "Reopen the project first" in r.get_json()["message"]


# --------------------------------------------------------------- overall performance
def test_project_reviews_view_and_overall_performance(client, world):
    submit(client, world, "m1", rid(world["main"], 1), **full())                                                   # 84/100
    submit(client, world, "m1", rid(world["main"], 2), criteria=[{"name": "A", "max_marks": 50, "marks_obtained": 25}], remarks="ok")   # 25/50
    put(client, world, "m1", rid(world["main"], 3), **full())                                                      # draft: excluded from totals
    d = client.get(f"/api/reviews/projects/{world['main'].id}", headers=world["H"]["m1"]).get_json()["data"]
    assert [r["status"] for r in d["reviews"]] == ["submitted", "submitted", "draft", "pending"]
    o = d["overall"]
    assert o["reviews_submitted"] == 2 and o["total_obtained"] == 109.0 and o["total_max"] == 150.0
    assert o["percentage"] == 72.67 and o["average_percentage"] == 67.0                                           # (84+50)/2
    assert [(x["week_no"], x["percentage"]) for x in o["reviews"]] == [(1, 84.0), (2, 50.0)]
    # the student sees only published reviews, and overall performance of those only
    s = client.get(f"/api/reviews/projects/{world['main'].id}", headers=world["H"]["s1"]).get_json()["data"]
    assert [r["visible"] for r in s["reviews"]] == [True, True, False, False] and s["overall"]["reviews_submitted"] == 2
    assert all("criteria" not in r for r in s["reviews"][2:])
    assert client.get(f"/api/reviews/projects/{world['main'].id}", headers=world["H"]["s2"]).status_code == 404
    assert client.get(f"/api/reviews/projects/{world['main'].id}", headers=world["H"]["la"]).status_code == 200


def test_summary_math_helper():
    from decimal import Decimal
    assert ev.to_decimal("7.255", "x") == Decimal("7.26") and ev.to_decimal(3, "x") == Decimal("3.00")
    with pytest.raises(Exception):
        ev.to_decimal("Infinity", "x")


def test_progress_includes_submitted_reviews(client, world):
    base = compute_progress(db.session.get(Project, world["main"].id))
    submit(client, world, "m1", rid(world["main"], 1), **full())
    submit(client, world, "m1", rid(world["main"], 2), **full())
    db.session.expire_all()
    assert compute_progress(db.session.get(Project, world["main"].id)) == base + 20


# ------------------------------------------------------------------ final evaluation
def test_final_evaluation_signoff_and_completion(client, world):
    p = world["main"]
    go = lambda who, to: client.post(f"/api/projects/{p.id}/transition", headers=world["H"][who], json={"to": to})  # noqa: E731
    sign = lambda who, remarks="Excellent project": client.post(f"/api/reviews/projects/{p.id}/final-signoff", headers=world["H"][who], json={"remarks": remarks})  # noqa: E731
    assert go("m1", "final_evaluation").status_code == 409                                  # reviews outstanding
    assert sign("m1").status_code == 409                                                    # wrong stage
    submit_all(client, world)
    r = go("m1", "final_evaluation")
    assert r.status_code == 200
    view = client.get(f"/api/reviews/projects/{p.id}", headers=world["H"]["m1"]).get_json()["data"]["final_evaluation"]
    assert view["can_sign_off"] is True and view["signed_off"] is False and view["all_reviews_submitted"] is True
    assert client.get(f"/api/reviews/projects/{p.id}", headers=world["H"]["s1"]).get_json()["data"]["final_evaluation"]["can_sign_off"] is False
    assert go("m1", "completed").status_code == 409                                         # cannot complete without sign-off
    assert sign("s1").status_code == 403 and sign("la").status_code == 403 and sign("m2").status_code == 404
    assert sign("m1", " ").status_code == 422
    db.session.query(Notification).delete()
    db.session.commit()
    r = sign("m1")
    assert r.status_code == 200
    assert sign("m1").status_code == 409                                                    # only once
    final = client.get(f"/api/reviews/projects/{p.id}", headers=world["H"]["s1"]).get_json()["data"]["final_evaluation"]
    assert final["signed_off"] and final["remarks"] == "Excellent project" and final["signed_by"] == "Mentor"
    assert db.session.query(Notification).filter_by(type="final_signed_off").count() == 2    # student + lead
    assert db.session.query(AuditLog).filter_by(action="project.final_signoff").count() == 1
    db.session.query(Notification).delete()
    db.session.commit()
    r = go("m1", "completed")
    assert r.status_code == 200 and r.get_json()["data"]["stage"] == "completed"
    assert db.session.query(Notification).filter_by(type="project_completed").count() == 2
    db.session.expire_all()
    assert compute_progress(db.session.get(Project, p.id)) == 70                             # SRS 20 + reviews 40 + final 10
    # admin reopening the project clears the sign-off so the final evaluation must be redone
    r = client.post(f"/api/projects/{p.id}/reopen", headers=world["H"]["admin"], json={"to": "implementation", "reason": "Marks to be revised"})
    assert r.status_code == 200 and db.session.get(Project, p.id).final_signed_off_by is None


def test_reopening_a_review_blocks_completion_until_resubmitted(client, world):
    p = world["main"]
    submit_all(client, world)
    client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["m1"], json={"to": "final_evaluation"})
    client.post(f"/api/reviews/projects/{p.id}/final-signoff", headers=world["H"]["m1"], json={"remarks": "Fine"})
    client.post(f"/api/reviews/{rid(p, 4)}/reopen", headers=world["H"]["m1"], json={"reason": "Fix week four"})
    r = client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["m1"], json={"to": "completed"})
    assert r.status_code == 409 and "four weekly reviews" in r.get_json()["message"]
    submit(client, world, "m1", rid(p, 4))
    assert client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["m1"], json={"to": "completed"}).status_code == 200


# ------------------------------------------------------------------------ templates
def test_sample_templates_are_editable_data_and_idempotent(client, world):
    h = world["H"]["m1"]
    r = client.post("/api/evaluation-criteria/templates/samples", headers=h)
    assert r.status_code == 201 and len(r.get_json()["data"]) == 4
    assert len(client.post("/api/evaluation-criteria/templates/samples", headers=h).get_json()["data"]) == 0
    lst = client.get("/api/evaluation-criteria/templates", headers=h).get_json()["data"]
    assert [t["total_marks"] for t in lst] == [100, 100, 100, 100] and lst[0]["week_no"] == 1
    # they can be changed/deleted like any other template
    tid = lst[0]["id"]
    r = client.put(f"/api/evaluation-criteria/templates/{tid}", headers=h, json={"name": "Mine", "week_no": 1, "criteria": [{"name": "Only", "max_marks": 5}]})
    assert r.get_json()["data"]["criteria"] == [{"name": "Only", "max_marks": 5.0}]
    assert client.delete(f"/api/evaluation-criteria/templates/{tid}", headers=h).status_code == 200
    assert len(client.get("/api/evaluation-criteria/templates", headers=h).get_json()["data"]) == 3
    assert len(client.get("/api/evaluation-criteria/templates?week=2", headers=h).get_json()["data"]) == 1


def test_templates_are_private_and_validated(client, world):
    h, other = world["H"]["m1"], world["H"]["m2"]
    t = client.post("/api/evaluation-criteria/templates", headers=h, json={"name": "T", "criteria": [{"name": "A", "max_marks": 10}]}).get_json()["data"]
    assert client.get("/api/evaluation-criteria/templates", headers=other).get_json()["data"] == []
    assert client.put(f"/api/evaluation-criteria/templates/{t['id']}", headers=other, json={"name": "x", "criteria": [{"name": "A", "max_marks": 1}]}).status_code == 404
    assert client.delete(f"/api/evaluation-criteria/templates/{t['id']}", headers=other).status_code == 404
    for body in ({"name": "", "criteria": [{"name": "A", "max_marks": 1}]}, {"name": "x", "criteria": []},
                 {"name": "x", "criteria": [{"name": "A", "max_marks": -1}]}, {"name": "x", "week_no": 9, "criteria": [{"name": "A", "max_marks": 1}]},
                 {"name": "x", "criteria": [{"name": "A", "max_marks": 1}, {"name": "a", "max_marks": 2}]}):
        assert client.post("/api/evaluation-criteria/templates", headers=h, json=body).status_code == 422, body
    for who in ("s1", "la", "admin"):
        assert client.get("/api/evaluation-criteria/templates", headers=world["H"][who]).status_code == 403


def test_apply_template_to_review(client, world):
    h = world["H"]["m1"]
    t = client.post("/api/evaluation-criteria/templates", headers=h, json={"name": "T", "criteria": [{"name": "Design", "max_marks": 40}, {"name": "Code", "max_marks": 60}]}).get_json()["data"]
    rv = rid(world["main"], 2)
    put(client, world, "m1", rv, criteria=[{"name": "Old", "max_marks": 5, "marks_obtained": 5}])
    r = client.post(f"/api/reviews/{rv}/apply-template", headers=h, json={"template_id": t["id"]})
    d = r.get_json()["data"]
    assert r.status_code == 200 and [(c["name"], c["max_marks"], c["marks_obtained"]) for c in d["criteria"]] == [("Design", 40.0, None), ("Code", 60.0, None)]
    assert d["status"] == "draft"
    # someone else's template, a submitted review, or a locked week are all refused
    assert client.post(f"/api/reviews/{rv}/apply-template", headers=world["H"]["m2"], json={"template_id": t["id"]}).status_code == 404
    assert client.post(f"/api/reviews/{rv}/apply-template", headers=h, json={"template_id": 9999}).status_code == 404
    submit(client, world, "m1", rid(world["main"], 1), **full())
    assert client.post(f"/api/reviews/{rid(world['main'], 1)}/apply-template", headers=h, json={"template_id": t["id"]}).status_code == 409
    assert client.post(f"/api/reviews/{rid(world['early'], 3)}/apply-template", headers=h, json={"template_id": t["id"]}).status_code == 409


# -------------------------------------------------------------------------- queue
def test_evaluation_queue_scoped_and_filtered(client, world):
    q = lambda who, qs="": client.get(f"/api/reviews/queue{qs}", headers=world["H"][who]).get_json()  # noqa: E731
    d = q("m1")
    assert d["meta"]["total"] == 5                                    # main weeks 1-4 + early week 1; 'fresh' is not evaluable
    assert {(i["project"]["title"], i["week_no"]) for i in d["data"]} >= {("Project main", 1), ("Project early", 1)}
    assert q("la")["meta"]["total"] == 5 and q("admin")["meta"]["total"] == 5
    assert q("m2")["meta"]["total"] == 0 and q("lb")["meta"]["total"] == 0
    assert q("m1", "?week=2")["meta"]["total"] == 1
    submit(client, world, "m1", rid(world["main"], 1), **full())
    put(client, world, "m1", rid(world["main"], 2), **full())
    assert q("m1")["meta"]["total"] == 4                              # submitted ones leave the queue
    assert q("m1", "?status=draft")["meta"]["total"] == 1
    r = db.session.get(ProjectReview, rid(world["main"], 3))
    from datetime import date, timedelta
    r.due_date = date.today() - timedelta(days=2)
    db.session.commit()
    od = q("m1", "?overdue=1")
    assert od["meta"]["total"] == 1 and od["data"][0]["is_overdue"] is True and od["data"][0]["week_no"] == 3
    assert client.get("/api/reviews/queue", headers=world["H"]["s1"]).status_code == 403


def test_reviews_require_authentication(client, world):
    rv = rid(world["main"], 1)
    assert client.get(f"/api/reviews/{rv}").status_code == 401
    assert client.put(f"/api/reviews/{rv}", json={}).status_code == 401
    assert client.get("/api/evaluation-criteria/templates").status_code == 401


def test_views_by_role(client, world):
    rv = rid(world["main"], 1)
    put(client, world, "m1", rv, **full())
    for who in ("m1", "la", "admin"):
        d = client.get(f"/api/reviews/{rv}", headers=world["H"][who]).get_json()["data"]
        assert d["visible"] and len(d["criteria"]) == 4, who                                  # monitors see drafts
    s = client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]
    assert s["visible"] is False and "criteria" not in s and "remarks" not in s               # students never see drafts
    assert client.get(f"/api/reviews/{rv}", headers=world["H"]["s2"]).status_code == 404       # nor other students' reviews
