import io

import pytest

from app.extensions import db
from app.models import AuditLog, Batch, Domain, OrganisationalUnit, ProjectReview, Student, User
from app.services import user_service
from tests.test_dashboard_reports import world  # noqa: F401  (shared multi-batch fixture)


def batch_id(code):
    return db.session.query(Batch).filter_by(code=code).one().id


def dash(client, world, who, qs=""):
    return client.get(f"/api/dashboard{qs}", headers=world["H"][who])


# --------------------------------------------------------------- dashboard batch filter
def test_admin_dashboard_narrows_to_one_batch(client, world):
    everything = dash(client, world, "admin").get_json()["data"]["counts"]
    b1 = dash(client, world, "admin", f"?batch_id={batch_id('B1')}").get_json()["data"]
    c = b1["counts"]
    assert (c["batches"], c["students"], c["mentors"], c["projects_total"], c["completed"], c["delayed"]) == (1, 4, 1, 3, 1, 1)
    assert (c["ous"], c["domains"], c["problem_statements"]) == (1, 1, 2)          # the batch's own OU / domain / domain statements
    assert {r["batch"] for r in b1["batch_progress"]} == {"B1"}
    assert [(p["ou"], p["with_project"], p["without_project"]) for p in b1["student_participation"]] == [("Retail OU", 3, 1)]
    assert {m["mentor"] for m in b1["mentor_workload"]} == {"Mia One"}
    assert sum(x["count"] for x in b1["stage_distribution"]) == 3
    b2 = dash(client, world, "admin", f"?batch_id={batch_id('B2')}").get_json()["data"]
    assert (b2["counts"]["projects_total"], b2["counts"]["students"], b2["counts"]["delayed"]) == (1, 1, 1)
    # the unfiltered view is the sum of its parts and is unchanged by the feature
    assert everything["projects_total"] == c["projects_total"] + b2["counts"]["projects_total"]
    assert everything["students"] == 5 and everything["batches"] == 2


def test_lead_and_mentor_dashboards_support_batch_filter_within_scope(client, world):
    b1, b2 = batch_id("B1"), batch_id("B2")
    lead = dash(client, world, "la", f"?batch_id={b1}").get_json()["data"]["counts"]
    assert (lead["batches"], lead["students"], lead["projects_allocated"], lead["completed"]) == (1, 4, 3, 1)
    assert dash(client, world, "la", f"?batch_id={b2}").status_code == 404                 # other domain's batch
    assert dash(client, world, "lb", f"?batch_id={b1}").status_code == 404
    mentor = dash(client, world, "m1", f"?batch_id={b1}").get_json()["data"]["counts"]
    assert (mentor["assigned_batches"], mentor["students"], mentor["reviews_completed"]) == (1, 3, 6)
    assert dash(client, world, "m1", f"?batch_id={b2}").status_code == 404                 # not their batch
    assert dash(client, world, "m3", f"?batch_id={b2}").status_code == 200


def test_batch_filter_ignored_for_students_and_missing_batch_is_404(client, world):
    assert dash(client, world, "s1", f"?batch_id={batch_id('B2')}").status_code == 200       # students always see only their own project
    assert dash(client, world, "admin", "?batch_id=99999").status_code == 404


def test_reviews_queue_batch_filter(client, world):
    q = lambda qs="": client.get(f"/api/reviews/queue{qs}", headers=world["H"]["admin"]).get_json()["meta"]["total"]  # noqa: E731
    total, one, two = q(), q(f"?batch_id={batch_id('B1')}"), q(f"?batch_id={batch_id('B2')}")
    assert one + two == total and one > 0 and two > 0


def test_list_endpoints_filter_by_batch(client, world):
    b1, b2 = batch_id("B1"), batch_id("B2")
    projects = lambda who, bid: client.get(f"/api/projects?batch_id={bid}", headers=world["H"][who]).get_json()["meta"]["total"]  # noqa: E731
    assert (projects("admin", b1), projects("admin", b2), projects("la", b1), projects("la", b2), projects("m1", b1)) == (3, 1, 3, 0, 3)
    assert client.get(f"/api/scrum/overview?batch_id={b1}", headers=world["H"]["m1"]).get_json()["meta"]["total"] == 3
    assert client.get(f"/api/srs/queue?batch_id={b1}", headers=world["H"]["admin"]).get_json()["meta"]["total"] == 1   # Beta awaiting review
    assert client.get(f"/api/srs/queue?batch_id={b2}", headers=world["H"]["admin"]).get_json()["meta"]["total"] == 0


# -------------------------------------------------------------------------- credentials
@pytest.fixture()
def batch_with_students(make_user, login, app):
    admin = make_user("admin", "admin@x.com")
    ou = db.session.query(OrganisationalUnit).first()
    batch = Batch(code="C1", name="Credential batch", ou_id=ou.id, domain_id=db.session.query(Domain).first().id)
    db.session.add(batch)
    db.session.flush()
    initial = {}
    for i in range(1, 4):
        s, pw = user_service.create_student(batch, f"Student {i}", f"c{i}@x.com", f"99900000{i}", f"REG{i}")
        initial[s.registration_no] = (s.id, pw)
    db.session.commit()
    return {"H": login("admin@x.com"), "batch": batch, "initial": initial, "login": login}


def issue(client, ctx, **body):
    return client.post("/api/students/credentials", headers=ctx["H"], json={"batch_id": ctx["batch"].id, **body})


def can_login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200


def test_issue_credentials_gives_working_shareable_passwords(client, batch_with_students):
    ctx = batch_with_students
    r = issue(client, ctx)
    d = r.get_json()["data"]
    assert r.status_code == 200 and len(d["credentials"]) == 3 and d["skipped"] == [] and d["batch"] == {"code": "C1", "name": "Credential batch"}
    row = next(c for c in d["credentials"] if c["registration_no"] == "REG2")
    assert set(row) == {"name", "email", "phone", "registration_no", "batch_code", "batch_name", "temporary_password"}
    assert (row["name"], row["email"], row["phone"], row["batch_code"], row["batch_name"]) == ("Student 2", "c2@x.com", "999000002", "C1", "Credential batch")
    # the issued password works and forces a change; the previous one no longer does
    old_pw = ctx["initial"]["REG2"][1]
    assert can_login(client, "c2@x.com", row["temporary_password"]) and not can_login(client, "c2@x.com", old_pw)
    me = client.post("/api/auth/login", json={"email": "c2@x.com", "password": row["temporary_password"]}).get_json()["data"]["user"]
    assert me["must_change_password"] is True


def test_students_who_already_chose_a_password_are_never_touched(client, batch_with_students):
    ctx = batch_with_students
    s1 = db.session.query(Student).filter_by(registration_no="REG1").one()
    s1.user.must_change_password = False                                  # REG1 already set their own password
    s3 = db.session.query(Student).filter_by(registration_no="REG3").one()
    s3.user.is_active = False
    db.session.commit()
    own_hash = s1.user.password_hash
    d = issue(client, ctx).get_json()["data"]
    assert [c["registration_no"] for c in d["credentials"]] == ["REG2"]
    reasons = {s["registration_no"]: s["reason"] for s in d["skipped"]}
    assert reasons == {"REG1": "Already set their own password", "REG3": "Account is deactivated"}
    db.session.expire_all()
    assert db.session.get(Student, s1.id).user.password_hash == own_hash
    assert can_login(client, "c1@x.com", ctx["initial"]["REG1"][1])       # still works


def test_issue_credentials_for_selected_students_only(client, batch_with_students):
    ctx = batch_with_students
    pick = [ctx["initial"]["REG1"][0], ctx["initial"]["REG3"][0]]
    d = issue(client, ctx, student_ids=pick).get_json()["data"]
    assert [c["registration_no"] for c in d["credentials"]] == ["REG1", "REG3"]
    assert can_login(client, "c2@x.com", ctx["initial"]["REG2"][1])        # unselected student untouched


def test_credentials_are_admin_only_audited_and_not_stored(client, batch_with_students, make_user):
    ctx = batch_with_students
    for role in ("domain_lead", "mentor", "student"):
        make_user(role, f"{role}@x.com")
        h = ctx["login"](f"{role}@x.com")
        assert client.post("/api/students/credentials", headers=h, json={"batch_id": ctx["batch"].id}).status_code == 403
    assert client.post("/api/students/credentials", json={"batch_id": ctx["batch"].id}).status_code == 401
    assert issue(client, ctx).status_code == 200
    log = db.session.query(AuditLog).filter_by(action="student.credentials_issued").one()
    assert log.details == {"issued": 3, "skipped": 0} and "password" not in str(log.details).lower()
    assert all(u.password_hash and not u.password_hash.startswith(("Pw", "plain")) for u in db.session.query(User).all())


def test_credentials_validation(client, batch_with_students):
    assert client.post("/api/students/credentials", headers=batch_with_students["H"], json={"batch_id": 9999}).status_code == 422
    assert client.post("/api/students/credentials", headers=batch_with_students["H"], json={}).status_code == 422


def test_import_confirmation_returns_full_shareable_details(client, make_user, login):
    make_user("admin", "admin@x.com")
    h = login("admin@x.com")
    ou = db.session.query(OrganisationalUnit).filter_by(code="RETAIL").one()
    dom = db.session.query(Domain).first()
    made = client.post("/api/batches", headers=h, json={"name": "Import batch", "ou_id": ou.id, "domain_id": dom.id,
                                                          "details": {"programme_name": "P"}})
    assert made.status_code == 201
    code = made.get_json()["data"]["code"]  # batch IDs are system-generated
    csv = f"Student Name,Email,Phone Number,Registration Number,Batch Code\nAsha K,asha@x.com,9999999999,R1,{code}\n"
    job = client.post("/api/imports/students", headers=h, content_type="multipart/form-data",
                      data={"ou_id": str(ou.id), "file": (io.BytesIO(csv.encode()), "s.csv")}).get_json()["data"]
    cred = client.post(f"/api/imports/{job['id']}/confirm", headers=h, json={}).get_json()["data"]["credentials"][0]
    assert (cred["name"], cred["email"], cred["phone"], cred["registration_no"], cred["batch_code"], cred["batch_name"]) == \
        ("Asha K", "asha@x.com", "9999999999", "R1", code, "Import batch")
    assert can_login(client, "asha@x.com", cred["temporary_password"])
