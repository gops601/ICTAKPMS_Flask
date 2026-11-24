from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Notification, ProjectReview, ReviewDateRequest
from tests.test_reviews import full, put, rid, submit, world  # noqa: F401

D = lambda days: (date.today() + timedelta(days=days)).isoformat()  # noqa: E731


def schedule(client, world, review_id, when):                                    # noqa: F811
    return put(client, world, "m1", review_id, review_date=when)


def ask(client, world, review_id, when, reason="Student is on leave that week", who="m1"):   # noqa: F811
    return client.post(f"/api/reviews/{review_id}/date-requests", headers=world["H"][who], json={"new_date": when, "reason": reason})


def decide(client, world, req_id, decision, note=None, who="la"):                # noqa: F811
    return client.post(f"/api/review-date-requests/{req_id}/decision", headers=world["H"][who], json={"decision": decision, "note": note})


@pytest.fixture()
def scheduled(client, world):                                                    # noqa: F811
    """Week 1 of the main project already has a mentor-assigned review date (10 days from now)."""
    rv = rid(world["main"], 1)
    assert schedule(client, world, rv, D(10)).status_code == 200
    return rv


# ============================================================ assigning the date, then locking it
def test_mentor_assigns_the_first_date_without_any_approval(client, world):    # noqa: F811
    rv = rid(world["main"], 1)
    r = schedule(client, world, rv, D(7))
    assert r.status_code == 200 and r.get_json()["data"]["review_date"] == D(7)
    assert db.session.query(ReviewDateRequest).count() == 0


def test_a_scheduled_date_cannot_be_edited_in_place(client, world, scheduled):   # noqa: F811
    r = put(client, world, "m1", scheduled, review_date=D(20))
    assert r.status_code == 422 and "review_date" in r.get_json()["errors"] and "Domain Lead must approve" in r.get_json()["message"]
    assert put(client, world, "m1", scheduled, review_date=None).status_code == 422          # nor cleared
    assert put(client, world, "m1", scheduled, review_date=D(10), remarks="same date again").status_code == 200   # unchanged date is fine
    assert db.session.get(ProjectReview, scheduled).review_date.isoformat() == D(10)
    r = submit(client, world, "m1", scheduled, **full(), review_date=D(30))
    assert r.status_code == 422                                                              # submit cannot sneak a new date in either
    assert db.session.get(ProjectReview, scheduled).status != "submitted"


def test_submitting_without_a_date_still_defaults_to_today(client, world):      # noqa: F811
    rv = rid(world["main"], 2)
    d = submit(client, world, "m1", rv, **full()).get_json()["data"]
    assert d["review_date"] == date.today().isoformat()


# ================================================================== requesting a change
def test_mentor_requests_a_change_and_the_domain_lead_is_notified(client, world, scheduled):   # noqa: F811
    db.session.query(Notification).delete()
    db.session.commit()
    r = ask(client, world, scheduled, D(14))
    d = r.get_json()["data"]
    assert r.status_code == 201 and d["status"] == "pending" and (d["old_date"], d["new_date"]) == (D(10), D(14))
    assert d["requested_by"] == "Mentor" and d["week_no"] == 1 and d["project"]["batch"]["code"] == "B1"
    assert db.session.get(ProjectReview, scheduled).review_date.isoformat() == D(10)          # nothing changes until approved
    la = db.session.query(Notification).filter_by(user_id=db.session.query(__import__("app.models", fromlist=["User"]).User).filter_by(email="la@x.com").one().id).one()
    assert la.type == "review_date_requested" and "Student is on leave" in la.message and la.link == "/lead/date-requests"
    assert db.session.query(Notification).filter_by(type="review_date_requested").count() == 1   # only the lead of THIS domain
    # the review now shows the pending request and blocks a second one
    view = client.get(f"/api/reviews/{scheduled}", headers=world["H"]["m1"]).get_json()["data"]
    assert view["date_request"]["new_date"] == D(14) and view["permissions"]["can_request_date_change"] is False
    assert ask(client, world, scheduled, D(15)).status_code == 409
    lead_view = client.get(f"/api/reviews/{scheduled}", headers=world["H"]["la"]).get_json()["data"]
    assert lead_view["permissions"]["can_decide_date_request"] is True and lead_view["date_request"]["id"] == d["id"]
    assert "date_request" not in client.get(f"/api/reviews/{scheduled}", headers=world["H"]["s1"]).get_json()["data"]


@pytest.mark.parametrize("payload,status,fragment", [
    ({"new_date": date.today().replace(year=date.today().year - 1).isoformat(), "reason": "Need more time"}, 422, "past"),
    ({"new_date": D(10), "reason": "Same date as now"}, 422, "already the scheduled"),
    ({"new_date": D(12), "reason": "no"}, 422, "reason"),
    ({"new_date": "not-a-date", "reason": "Valid reason"}, 422, "date"),
])
def test_request_validation(client, world, scheduled, payload, status, fragment):   # noqa: F811
    r = client.post(f"/api/reviews/{scheduled}/date-requests", headers=world["H"]["m1"], json=payload)
    assert r.status_code == status and fragment in r.get_json()["message"].lower()
    assert db.session.query(ReviewDateRequest).count() == 0


def test_a_date_must_be_scheduled_before_a_change_can_be_requested(client, world):   # noqa: F811
    r = ask(client, world, rid(world["main"], 3), D(12))
    assert r.status_code == 409 and "no approval is needed" in r.get_json()["message"]


def test_submitted_reviews_cannot_be_rescheduled(client, world, scheduled):      # noqa: F811
    submit(client, world, "m1", scheduled, **full())
    assert ask(client, world, scheduled, D(20)).status_code == 409


def test_only_the_assigned_mentor_can_ask(client, world, scheduled):             # noqa: F811
    assert ask(client, world, scheduled, D(14), who="m2").status_code == 404        # unassigned mentor sees nothing
    for who in ("la", "admin", "s1"):
        assert ask(client, world, scheduled, D(14), who=who).status_code == 403
    assert client.post(f"/api/reviews/{scheduled}/date-requests", json={"new_date": D(14), "reason": "Valid reason"}).status_code == 401
    assert db.session.query(ReviewDateRequest).count() == 0


# ===================================================================== approval by the lead
def test_domain_lead_approves_and_the_new_date_takes_effect(client, world, scheduled):   # noqa: F811
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    before = db.session.get(ProjectReview, scheduled).version
    db.session.query(Notification).delete()
    db.session.commit()
    r = decide(client, world, req["id"], "approve", "Fine, agreed")
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["status"] == "approved" and d["decided_by"] == "Domain_Lead" and d["decision_note"] == "Fine, agreed"
    review = db.session.get(ProjectReview, scheduled)
    assert review.review_date.isoformat() == D(14) and review.version == before + 1
    kinds = lambda uid: {n.type for n in db.session.query(Notification).filter_by(user_id=uid)}  # noqa: E731
    assert "review_date_approved" in kinds(world["m1u"].id) and "review_rescheduled" in kinds(world["s1u"].id)
    assert any("scheduled for " + D(14) in n.message for n in db.session.query(Notification).filter_by(user_id=world["s1u"].id))
    assert db.session.query(AuditLog).filter_by(action="review.date_approved", entity_id=scheduled).count() == 1
    # students can now see the scheduled date, the mentor can ask again, and the lock still applies
    stu = client.get(f"/api/reviews/{scheduled}", headers=world["H"]["s1"]).get_json()["data"]
    assert stu["visible"] is False and stu["review_date"] == D(14)
    assert client.get(f"/api/reviews/{scheduled}", headers=world["H"]["m1"]).get_json()["data"]["permissions"]["can_request_date_change"] is True
    assert put(client, world, "m1", scheduled, review_date=D(40)).status_code == 422


def test_rejection_needs_a_reason_and_keeps_the_old_date(client, world, scheduled):   # noqa: F811
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    assert decide(client, world, req["id"], "reject").status_code == 422
    assert decide(client, world, req["id"], "reject", "ok").status_code == 422
    db.session.query(Notification).delete()
    db.session.commit()
    r = decide(client, world, req["id"], "reject", "Please keep the original date")
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "rejected"
    assert db.session.get(ProjectReview, scheduled).review_date.isoformat() == D(10)
    n = db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="review_date_rejected").one()
    assert "Please keep the original date" in n.message
    assert db.session.query(Notification).filter_by(user_id=world["s1u"].id).count() == 0     # students are not bothered by rejections
    assert ask(client, world, scheduled, D(16)).status_code == 201                              # a new request is allowed


def test_decision_permissions_and_idempotency(client, world, scheduled):         # noqa: F811
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    assert decide(client, world, req["id"], "approve", who="m1").status_code == 403           # the mentor cannot approve their own request
    assert decide(client, world, req["id"], "approve", who="s1").status_code == 403
    assert decide(client, world, req["id"], "approve", who="lb").status_code == 404           # lead of another domain
    assert decide(client, world, req["id"], "maybe").status_code == 422
    assert decide(client, world, 9999, "approve").status_code == 404
    assert db.session.get(ReviewDateRequest, req["id"]).status == "pending"
    assert decide(client, world, req["id"], "approve", who="admin").status_code == 200        # admin may decide when needed
    assert decide(client, world, req["id"], "approve").status_code == 409                     # cannot be decided twice
    assert decide(client, world, req["id"], "reject", "late").status_code == 409


def test_cannot_approve_after_the_review_was_submitted(client, world, scheduled):   # noqa: F811
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    submit(client, world, "m1", scheduled, **full())
    r = decide(client, world, req["id"], "approve")
    assert r.status_code == 409 and "already been submitted" in r.get_json()["message"]
    assert db.session.get(ProjectReview, scheduled).review_date.isoformat() == D(10)


# ======================================================================= withdrawing
def test_mentor_can_withdraw_a_pending_request(client, world, scheduled):        # noqa: F811
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    cancel = lambda who: client.post(f"/api/review-date-requests/{req['id']}/cancel", headers=world["H"][who])  # noqa: E731
    assert cancel("la").status_code == 403 and cancel("s1").status_code == 403
    assert cancel("m2").status_code == 404
    r = cancel("m1")
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "cancelled"
    assert cancel("m1").status_code == 409
    assert decide(client, world, req["id"], "approve").status_code == 409                    # a withdrawn request cannot be approved
    assert ask(client, world, scheduled, D(15)).status_code == 201


# ==================================================================== lists & history
def test_queue_is_scoped_filtered_and_pending_first(client, world, scheduled):   # noqa: F811
    other = rid(world["main"], 2)
    schedule(client, world, other, D(9))
    first = ask(client, world, scheduled, D(14)).get_json()["data"]
    decide(client, world, first["id"], "reject", "Not now")
    second = ask(client, world, other, D(12)).get_json()["data"]
    lst = lambda who, qs="": client.get(f"/api/review-date-requests{qs}", headers=world["H"][who])  # noqa: E731
    d = lst("la").get_json()
    assert [x["id"] for x in d["data"]] == [second["id"], first["id"]]                        # pending first, newest first
    assert d["meta"]["total"] == 2 and d["data"][0]["project"]["students"] == ["Student"]
    assert [x["id"] for x in lst("la", "?status=rejected").get_json()["data"]] == [first["id"]]
    assert [x["id"] for x in lst("la", "?week=2").get_json()["data"]] == [second["id"]]
    assert lst("la", "?batch_id=999").get_json()["meta"]["total"] == 0
    assert lst("admin").get_json()["meta"]["total"] == 2 and lst("m1").get_json()["meta"]["total"] == 2
    assert lst("lb").get_json()["meta"]["total"] == 0 and lst("m2").get_json()["meta"]["total"] == 0
    assert lst("s1").status_code == 403 and client.get("/api/review-date-requests").status_code == 401


def test_review_history_lists_every_request(client, world, scheduled):          # noqa: F811
    a = ask(client, world, scheduled, D(14)).get_json()["data"]
    decide(client, world, a["id"], "approve")
    ask(client, world, scheduled, D(18), "Clash with exams")
    h = client.get(f"/api/reviews/{scheduled}/date-requests", headers=world["H"]["la"]).get_json()["data"]
    assert [(x["status"], x["new_date"]) for x in h] == [("pending", D(18)), ("approved", D(14))]
    assert client.get(f"/api/reviews/{scheduled}/date-requests", headers=world["H"]["s1"]).status_code == 403
    assert client.get(f"/api/reviews/{scheduled}/date-requests", headers=world["H"]["lb"]).status_code == 404


def test_lead_dashboard_counts_pending_requests(client, world, scheduled):      # noqa: F811
    count = lambda: client.get("/api/dashboard", headers=world["H"]["la"]).get_json()["data"]["counts"]["date_requests_pending"]  # noqa: E731
    assert count() == 0
    req = ask(client, world, scheduled, D(14)).get_json()["data"]
    assert count() == 1
    decide(client, world, req["id"], "approve")
    assert count() == 0


# ================================================ the mentor's button and the students' notifications
def test_mentor_can_request_a_date_change_whenever_the_review_is_open(client, world, scheduled):   # noqa: F811
    d = client.get(f"/api/reviews/{scheduled}", headers=world["H"]["m1"]).get_json()["data"]
    assert d["permissions"]["can_request_date_change"] is True
    assert ask(client, world, scheduled, D(14)).status_code == 201
    d = client.get(f"/api/reviews/{scheduled}", headers=world["H"]["m1"]).get_json()["data"]
    assert d["permissions"]["can_request_date_change"] is False                 # one request at a time
    for who in ("la", "admin"):
        assert client.get(f"/api/reviews/{scheduled}", headers=world["H"][who]).get_json()["data"]["permissions"]["can_request_date_change"] is False


def test_students_are_told_when_a_date_is_first_set_and_when_it_moves(client, world):   # noqa: F811
    rv = rid(world["main"], 1)
    db.session.query(Notification).delete()
    db.session.commit()
    assert schedule(client, world, rv, D(10)).status_code == 200
    mine = lambda t: [n for n in db.session.query(Notification).filter_by(user_id=world["s1u"].id, type=t)]   # noqa: E731
    assert len(mine("review_scheduled")) == 1 and D(10) in mine("review_scheduled")[0].message
    req = ask(client, world, rv, D(14)).get_json()["data"]["id"]
    assert not mine("review_rescheduled")                                       # nothing moves until it is approved
    assert decide(client, world, req, "approve").status_code == 200
    moved = mine("review_rescheduled")
    assert len(moved) == 1 and D(10) in moved[0].message and D(14) in moved[0].message
