import io

import pytest
from openpyxl import load_workbook

from app.extensions import db
from app.models import (AuditLog, Batch, EvaluationCriterion, EvaluationRevision, EvaluationScore, Notification, ProjectReview,
                        ProjectStudent, ReviewStudentRemark, Student)
from tests.test_dashboard_reports import world as report_world  # noqa: F401
from tests.test_reviews import full, put, rid, submit, world  # noqa: F401


# ===================================================================== only mentors score
@pytest.mark.parametrize("who", ["admin", "la", "lb", "s1", "m2"])
def test_nobody_but_the_assigned_mentor_can_score(client, world, who):          # noqa: F811
    rv = rid(world["main"], 1)
    assert put(client, world, who, rv, **full()).status_code in (403, 404)
    assert submit(client, world, who, rv, **full()).status_code in (403, 404)
    assert client.post(f"/api/reviews/{rv}/apply-template", headers=world["H"][who], json={"template_id": 1}).status_code in (403, 404)
    assert db.session.query(ProjectReview).filter_by(id=rv).one().status == "pending"


def test_permission_flags_make_the_rule_visible_to_the_ui(client, world):       # noqa: F811
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full())
    flags = lambda who: client.get(f"/api/reviews/{rv}", headers=world["H"][who]).get_json()["data"]["permissions"]  # noqa: E731
    assert flags("la")["can_edit"] is False and flags("la")["can_reopen"] is True          # lead: cannot score, can revert
    assert flags("admin")["can_edit"] is False
    assert flags("m1")["can_edit"] is False and flags("m1")["can_reopen"] is True


# ============================================================ domain lead reverts to mentor
def revert(client, world, who, rv, reason="Marks look too generous, please re-check"):
    return client.post(f"/api/reviews/{rv}/reopen", headers=world["H"][who], json={"reason": reason})


def test_domain_lead_reverts_a_score_to_the_mentor_for_updating(client, world):  # noqa: F811
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full())
    db.session.query(Notification).delete()
    db.session.commit()
    r = revert(client, world, "la", rv)
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "reopened" and d["revert_note"]["by_role"] == "domain_lead"
    assert d["revert_note"]["reason"] == "Marks look too generous, please re-check" and d["permissions"]["can_edit"] is False
    # the mentor is told (with the reason and a link to the review); the student is told it is under revision
    n = db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="review_reverted").one()
    assert "Marks look too generous" in n.message and n.link == f"/reviews/{rv}" and "Domain Lead" in n.message
    assert db.session.query(Notification).filter_by(user_id=world["s1u"].id, type="review_reopened").count() == 1
    # the mentor sees why it came back, can update the score and resubmit; the student never sees the revert note
    seen = client.get(f"/api/reviews/{rv}", headers=world["H"]["m1"]).get_json()["data"]
    assert seen["revert_note"]["reason"] and seen["permissions"]["can_edit"] is True
    assert client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]["visible"] is False
    crit = seen["criteria"]
    crit[0]["marks_obtained"] = 12
    assert put(client, world, "m1", rv, criteria=crit).status_code == 200
    assert submit(client, world, "m1", rv).get_json()["data"]["summary"]["total_obtained"] == 81.0     # 84 - 15 + 12
    assert client.get(f"/api/reviews/{rv}", headers=world["H"]["m1"]).get_json()["data"]["revert_note"] is None
    # the history shows what the score was before it was sent back
    rev = client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["la"]).get_json()["data"][0]
    assert rev["reason"].startswith("Marks look") and rev["snapshot"]["summary"]["total_obtained"] == 84.0
    assert db.session.query(AuditLog).filter_by(action="review.reopen", entity_id=rv).count() == 1


def test_revert_rules(client, world):                                           # noqa: F811
    rv = rid(world["main"], 1)
    assert revert(client, world, "la", rv).status_code == 409                    # nothing submitted yet
    submit(client, world, "m1", rv, **full())
    assert revert(client, world, "la", rv, "no").status_code == 422              # reason required
    assert revert(client, world, "lb", rv).status_code == 404                    # lead of another domain
    assert revert(client, world, "s1", rv).status_code == 403
    assert db.session.query(EvaluationRevision).count() == 0
    assert revert(client, world, "la", rv).status_code == 200
    assert revert(client, world, "la", rv).status_code == 409                    # already reopened
    assert put(client, world, "la", rv, remarks="x").status_code == 403          # a lead still cannot score it
    rv2 = rid(world["main"], 2)
    db.session.get(ProjectReview, rv2).status = "submitted"
    world["main"].stage = "completed"
    db.session.commit()
    assert revert(client, world, "la", rv2).status_code == 409                   # project completed: reopen the project first


def test_reverted_review_blocks_completion_until_resubmitted(client, world):     # noqa: F811
    p = world["main"]
    for w in range(1, 5):
        submit(client, world, "m1", rid(p, w), **full())
    client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["m1"], json={"to": "final_evaluation"})
    assert revert(client, world, "la", rid(p, 3)).status_code == 200
    client.post(f"/api/reviews/projects/{p.id}/final-signoff", headers=world["H"]["m1"], json={"remarks": "ok"})
    assert client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["m1"], json={"to": "completed"}).status_code == 409


# ============================================================ per-student remarks
@pytest.fixture()
def team(world, make_user, login):                                              # noqa: F811
    """The 'main' project becomes a team of two: s1 + s4."""
    u4 = make_user("student", "s4@x.com", name="Fourth Student")
    db.session.flush()
    batch = db.session.get(Batch, world["main"].batch_id)
    s4 = Student(user_id=u4.id, batch_id=batch.id, registration_no="S4")
    db.session.add(s4)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=world["main"].id, student_id=s4.id))
    db.session.commit()
    s1 = db.session.query(Student).filter_by(user_id=world["s1u"].id).one()
    world["H"]["s4"] = login("s4@x.com")
    return {"s1": s1.id, "s4": s4.id}


def test_mentor_sees_a_remark_box_for_every_student_and_saves_individual_remarks(client, world, team):   # noqa: F811
    rv = rid(world["main"], 1)
    d = client.get(f"/api/reviews/{rv}", headers=world["H"]["m1"]).get_json()["data"]
    assert [(r["name"], r["remarks"]) for r in d["student_remarks"]] == [("Student", ""), ("Fourth Student", "")]
    r = put(client, world, "m1", rv, **full(), student_remarks=[{"student_id": team["s1"], "remarks": "Led the design well"},
                                                                  {"student_id": team["s4"], "remarks": "Needs to contribute more code"}])
    got = {x["student_id"]: x["remarks"] for x in r.get_json()["data"]["student_remarks"]}
    assert got == {team["s1"]: "Led the design well", team["s4"]: "Needs to contribute more code"}
    # editing / clearing a remark
    r = put(client, world, "m1", rv, student_remarks=[{"student_id": team["s1"], "remarks": ""}, {"student_id": team["s4"], "remarks": "Improving"}])
    got = {x["student_id"]: x["remarks"] for x in r.get_json()["data"]["student_remarks"]}
    assert got == {team["s1"]: "", team["s4"]: "Improving"} and db.session.query(ReviewStudentRemark).count() == 1


def test_each_student_sees_only_their_own_remark_after_submission(client, world, team):    # noqa: F811
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full(), student_remarks=[{"student_id": team["s1"], "remarks": "Great leadership"},
                                                                {"student_id": team["s4"], "remarks": "Please commit more often"}])
    s1 = client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]
    s4 = client.get(f"/api/reviews/{rv}", headers=world["H"]["s4"]).get_json()["data"]
    assert [r["remarks"] for r in s1["student_remarks"]] == ["Great leadership"]
    assert [r["remarks"] for r in s4["student_remarks"]] == ["Please commit more often"]
    assert "Please commit more often" not in str(s1) and "Great leadership" not in str(s4)
    assert s1["remarks"] == "Good work"                                                     # shared overall feedback is visible to both
    lead = client.get(f"/api/reviews/{rv}", headers=world["H"]["la"]).get_json()["data"]
    assert len(lead["student_remarks"]) == 2                                                # monitors see everyone's


def test_student_remarks_are_validated_and_frozen_after_submission(client, world, team):   # noqa: F811
    rv = rid(world["main"], 1)
    outsider = db.session.query(Student).filter_by(registration_no="S2").one().id
    r = put(client, world, "m1", rv, student_remarks=[{"student_id": outsider, "remarks": "hi"}])
    assert r.status_code == 422 and "student_remarks.0" in r.get_json()["errors"]
    assert put(client, world, "m1", rv, student_remarks=[{"student_id": team["s1"], "remarks": "x" * 2001}]).status_code == 422
    assert db.session.query(ReviewStudentRemark).count() == 0
    submit(client, world, "m1", rv, **full(), student_remarks=[{"student_id": team["s1"], "remarks": "Solid"}])
    assert put(client, world, "m1", rv, student_remarks=[{"student_id": team["s1"], "remarks": "Changed"}]).status_code == 409
    assert db.session.query(ReviewStudentRemark).one().remarks == "Solid"


def test_student_remarks_are_kept_in_the_revert_history(client, world, team):   # noqa: F811
    rv = rid(world["main"], 1)
    submit(client, world, "m1", rv, **full(), student_remarks=[{"student_id": team["s4"], "remarks": "Original remark"}])
    revert(client, world, "la", rv)
    rev = client.get(f"/api/reviews/{rv}/revisions", headers=world["H"]["m1"]).get_json()["data"][0]
    assert any(r["remarks"] == "Original remark" for r in rev["snapshot"]["student_remarks"])


def test_solo_student_gets_their_own_remark_too(client, world):                  # noqa: F811
    rv = rid(world["main"], 1)
    d = client.get(f"/api/reviews/{rv}", headers=world["H"]["m1"]).get_json()["data"]
    sid = d["student_remarks"][0]["student_id"]
    submit(client, world, "m1", rv, **full(), student_remarks=[{"student_id": sid, "remarks": "Excellent individual effort"}])
    mine = client.get(f"/api/reviews/{rv}", headers=world["H"]["s1"]).get_json()["data"]
    assert mine["student_remarks"][0]["remarks"] == "Excellent individual effort"


# ============================================================== detailed batch report
def detailed(client, world, who, batch_code="B1", qs=""):
    bid = db.session.query(Batch).filter_by(code=batch_code).one().id
    return client.get(f"/api/reports/batch-detailed/{bid}{qs}", headers=world["H"][who])


def test_detailed_batch_report_workbook(client, report_world):                    # noqa: F811
    r = detailed(client, report_world, "admin")
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype
    assert r.headers["Content-Disposition"].startswith('attachment; filename="B1_detailed_report_')
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["Summary", "Students", "Weekly scores", "Criteria scores"]
    summary = {row[0].value: row[1].value for row in wb["Summary"].iter_rows(min_row=3) if row[0].value}
    assert (summary["Batch code"], summary["Students"], summary["Projects"], summary["Completed"], summary["Delayed"]) == ("B1", 4, 3, 1, 1)
    assert summary["Mentors"] == "Mia One" and summary["Generated by"] == "Admin"
    students = list(wb["Students"].iter_rows(values_only=True))
    header, rows = students[0], students[1:]
    assert header[:2] == ("Student", "Reg. no") and "Week 4 %" in header and "Final remarks" in header and len(rows) == 4
    col = {h: i for i, h in enumerate(header)}
    s1 = next(x for x in rows if x[col["Reg. no"]] == "S1")
    assert (s1[col["Project"]], s1[col["Stage"]], s1[col["Progress %"]], s1[col["Week 1 %"]], s1[col["Week 2 %"]], s1[col["Week 3 %"]],
            s1[col["Overall score %"]], s1[col["GitHub"]], s1[col["Tasks done"]], s1[col["Delayed"]]) == \
        ("Alpha", "Implementation", 57.5, 80.0, 50.0, None, 65.0, "https://github.com/o/alpha", "1/2", "Yes")
    s4 = next(x for x in rows if x[col["Reg. no"]] == "S4")
    assert s4[col["Project"]] == "Not allocated"
    weekly = list(wb["Weekly scores"].iter_rows(values_only=True))
    wcol = {h: i for i, h in enumerate(weekly[0])}
    assert len(weekly) - 1 == 12                                              # 3 projects x 4 weeks
    a_w2 = next(x for x in weekly[1:] if x[wcol["Project"]] == "Alpha" and x[wcol["Week"]] == "Week 2")
    assert (a_w2[wcol["Marks"]], a_w2[wcol["Out of"]], a_w2[wcol["%"]], a_w2[wcol["Overall feedback"]], a_w2[wcol["Status"]]) == (50.0, 100.0, 50.0, "Needs work", "Submitted")
    a_w3 = next(x for x in weekly[1:] if x[wcol["Project"]] == "Alpha" and x[wcol["Week"]] == "Week 3")
    assert a_w3[wcol["Marks"]] is None and a_w3[wcol["Status"]] == "Pending"
    criteria = list(wb["Criteria scores"].iter_rows(values_only=True))
    assert len(criteria) - 1 == 6 and criteria[0][4:7] == ("Criterion", "Max marks", "Marks obtained")


def test_detailed_report_includes_personal_remarks_but_never_draft_scores(client, report_world):   # noqa: F811
    w = report_world
    alpha_w1 = db.session.query(ProjectReview).filter_by(project_id=w["p1"].id, week_no=1).one()
    s1 = db.session.query(Student).filter_by(registration_no="S1").one()
    db.session.add(ReviewStudentRemark(review_id=alpha_w1.id, student_id=s1.id, remarks="Very consistent"))
    draft = db.session.query(ProjectReview).filter_by(project_id=w["p1"].id, week_no=3).one()
    draft.status, draft.remarks = "draft", "UNPUBLISHED NOTES"
    c = EvaluationCriterion(review_id=draft.id, name="Draft criterion", max_marks=10)
    db.session.add(c)
    db.session.flush()
    db.session.add(EvaluationScore(criterion_id=c.id, marks_obtained=9))
    db.session.commit()
    wb = load_workbook(io.BytesIO(detailed(client, w, "admin").data))
    weekly = list(wb["Weekly scores"].iter_rows(values_only=True))
    wcol = {h: i for i, h in enumerate(weekly[0])}
    w1 = next(x for x in weekly[1:] if x[wcol["Project"]] == "Alpha" and x[wcol["Week"]] == "Week 1")
    assert w1[wcol["Remarks for this student"]] == "Very consistent"
    w3 = next(x for x in weekly[1:] if x[wcol["Project"]] == "Alpha" and x[wcol["Week"]] == "Week 3")
    assert w3[wcol["Status"]] == "In progress" and w3[wcol["Marks"]] is None and w3[wcol["Overall feedback"]] is None
    everything = " ".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
    assert "UNPUBLISHED NOTES" not in everything and "Draft criterion" not in everything


def test_detailed_report_access_and_scope(client, report_world):                  # noqa: F811
    assert detailed(client, report_world, "la").status_code == 200                # lead of the batch's domain
    assert detailed(client, report_world, "la", "B2").status_code == 404          # another domain's batch
    assert detailed(client, report_world, "lb").status_code == 404
    assert detailed(client, report_world, "lb", "B2").status_code == 200
    for who in ("m1", "s1"):
        assert detailed(client, report_world, who).status_code == 403
    assert client.get("/api/reports/batch-detailed/1").status_code == 401
    assert client.get("/api/reports/batch-detailed/99999", headers=report_world["H"]["admin"]).status_code == 404


def test_detailed_report_formats_audit_and_injection_guard(client, report_world):  # noqa: F811
    for sheet, header in (("students", "Student,Reg. no"), ("weekly", "Student,Reg. no,Project,Week"), ("criteria", "Student,Reg. no,Project,Week,Criterion")):
        r = detailed(client, report_world, "admin", qs=f"?format=csv&sheet={sheet}")
        assert r.status_code == 200 and r.data.decode("utf-8-sig").startswith(header) and r.headers["Content-Disposition"].endswith(f'{sheet}.csv"')
    assert detailed(client, report_world, "admin", qs="?format=csv&sheet=nope").status_code == 422
    assert detailed(client, report_world, "admin", qs="?format=pdf").status_code == 422
    j = detailed(client, report_world, "admin", qs="?format=json").get_json()["data"]
    assert set(j["sheets"]) == {"students", "weekly", "criteria"} and len(j["sheets"]["students"]["rows"]) == 4
    assert db.session.query(AuditLog).filter_by(action="report.export", entity_type="batch").count() == 3
    report_world["users"]["s4"].name = '=HYPERLINK("http://evil","x")'
    db.session.commit()
    csv_text = detailed(client, report_world, "admin", qs="?format=csv&sheet=students").data.decode("utf-8-sig")
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text
