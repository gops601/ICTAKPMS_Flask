import pytest

from app.extensions import db
from app.models import Batch, Domain, OrganisationalUnit


@pytest.fixture()
def admin(make_user, login):
    make_user("admin", "admin@x.com")
    return login("admin@x.com")


def ou(code):
    return db.session.query(OrganisationalUnit).filter_by(code=code).one()


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


def batch_body(**kw):
    body = {"code": "B-001", "name": "Batch One", "ou_id": ou("ACADEMIC").id, "domain_id": domain("AIML").id,
            "start_date": "2026-01-05", "end_date": "2026-02-05",
            "details": {"university": "Kerala Uni", "college": "CET", "programme": "BTech"}}
    body.update(kw)
    return body


# ----------------------------------------------------------------------------- OUs
def test_seeded_ous_and_fields_exposed(client, admin):
    r = client.get("/api/ous", headers=admin)
    assert {o["code"] for o in r.get_json()["data"]} == {"RETAIL", "ACADEMIC", "CORPORATE", "GOVERNMENT"}
    fields = client.get(f"/api/ous/{ou('ACADEMIC').id}/fields?scope=batch", headers=admin).get_json()["data"]
    assert "university" in {f["field_key"] for f in fields}


def test_create_ou_and_duplicate(client, admin):
    r = client.post("/api/ous", headers=admin, json={"name": "Healthcare OU", "code": "HEALTH"})
    assert r.status_code == 201
    assert client.post("/api/ous", headers=admin, json={"name": "healthcare ou", "code": "H2"}).status_code == 409


def test_new_ou_supports_custom_fields_without_code_changes(client, admin):
    oid = client.post("/api/ous", headers=admin, json={"name": "Healthcare OU", "code": "HEALTH"}).get_json()["data"]["id"]
    f = client.post(f"/api/ous/{oid}/fields", headers=admin,
                    json={"label": "Hospital Name", "is_required": True})
    assert f.status_code == 201 and f.get_json()["data"]["field_key"] == "hospital_name"
    # duplicate key rejected
    assert client.post(f"/api/ous/{oid}/fields", headers=admin, json={"label": "Hospital Name"}).status_code == 409
    # select without options rejected
    assert client.post(f"/api/ous/{oid}/fields", headers=admin,
                       json={"label": "Tier", "field_type": "select"}).status_code == 422
    # new batch under this OU requires the new field
    body = batch_body(ou_id=oid, details={})
    r = client.post("/api/batches", headers=admin, json=body)
    assert r.status_code == 422 and "details.hospital_name" in r.get_json()["errors"]
    body["details"] = {"hospital_name": "KIMS"}
    assert client.post("/api/batches", headers=admin, json=body).status_code == 201


def test_deactivated_ou_blocks_new_batches(client, admin):
    oid = ou("RETAIL").id
    client.patch(f"/api/ous/{oid}/active", headers=admin, json={"is_active": False})
    r = client.post("/api/batches", headers=admin, json=batch_body(ou_id=oid, details={"programme_name": "X"}))
    assert r.status_code == 422


def test_ou_endpoints_admin_only_for_writes(client, make_user, login):
    make_user("domain_lead", "l@x.com")
    h = login("l@x.com")
    assert client.get("/api/ous", headers=h).status_code == 200
    assert client.post("/api/ous", headers=h, json={"name": "Nope OU", "code": "NOPE"}).status_code == 403


# --------------------------------------------------------------------------- Domains
def test_domain_crud_and_leads(client, admin, make_user):
    lead = make_user("domain_lead", "lead@x.com")
    r = client.post("/api/domains", headers=admin, json={"name": "Robotics", "code": "ROBO"})
    did = r.get_json()["data"]["id"]
    assert client.post("/api/domains", headers=admin, json={"name": "robotics", "code": "R2"}).status_code == 409
    r = client.put(f"/api/domains/{did}/leads", headers=admin, json={"user_ids": [lead.id]})
    assert r.get_json()["data"]["leads"][0]["email"] == "lead@x.com"
    # a non-lead user cannot be assigned
    admin_user = make_user("mentor", "m@x.com")
    assert client.put(f"/api/domains/{did}/leads", headers=admin, json={"user_ids": [admin_user.id]}).status_code == 422
    # removing leads
    r = client.put(f"/api/domains/{did}/leads", headers=admin, json={"user_ids": []})
    assert r.get_json()["data"]["leads"] == []


def test_domain_lead_sees_only_own_domain(client, admin, make_user, login):
    lead = make_user("domain_lead", "lead@x.com")
    client.put(f"/api/domains/{domain('AIML').id}/leads", headers=admin, json={"user_ids": [lead.id]})
    h = login("lead@x.com")
    names = [d["code"] for d in client.get("/api/domains", headers=h).get_json()["data"]]
    assert names == ["AIML"]
    assert client.get(f"/api/domains/{domain('IOT').id}", headers=h).status_code == 404


# ---------------------------------------------------------------------------- Batches
def test_create_batch_and_details_roundtrip(client, admin):
    r = client.post("/api/batches", headers=admin, json=batch_body())
    assert r.status_code == 201
    bid = r.get_json()["data"]["id"]
    d = client.get(f"/api/batches/{bid}", headers=admin).get_json()["data"]
    assert d["details"]["college"] == "CET" and d["domain"]["name"] == "AI & ML" and d["student_count"] == 0


def test_batch_validation_errors(client, admin):
    bad = batch_body(code="  ", name="  ", start_date="2026-03-01", end_date="2026-01-01", details={"bogus": "x"})
    r = client.post("/api/batches", headers=admin, json=bad)
    errs = r.get_json()["errors"]
    assert r.status_code == 422
    assert {"name", "end_date", "details.bogus", "details.university"} <= set(errs)
    assert "code" not in errs  # a blank batch code is replaced by a generated ICT_BATCH_ id


def test_batch_id_is_generated_from_the_domain_short_code(client, admin):
    import re
    a = client.post("/api/batches", headers=admin, json=batch_body()).get_json()["data"]
    b = client.post("/api/batches", headers=admin, json=batch_body(code="B-001")).get_json()["data"]  # supplied code is ignored
    c = client.post("/api/batches", headers=admin, json=batch_body(domain_id=domain("IOT").id)).get_json()["data"]
    assert re.fullmatch(r"ICT_AIML_[A-Z2-9]{6}", a["code"]) and re.fullmatch(r"ICT_AIML_[A-Z2-9]{6}", b["code"])
    assert re.fullmatch(r"ICT_IOT_[A-Z2-9]{6}", c["code"]) and a["code"] != b["code"]
    assert a["code"] != "B-001"
    # the ID never changes, even when the batch is edited or moved to another domain
    r = client.put(f"/api/batches/{a['id']}", headers=admin, json={"code": "HACK", "name": "Renamed", "domain_id": domain("IOT").id})
    assert r.status_code == 200 and r.get_json()["data"]["code"] == a["code"]


def test_update_batch_cannot_change_ou_and_can_change_domain(client, admin):
    bid = client.post("/api/batches", headers=admin, json=batch_body()).get_json()["data"]["id"]
    assert client.put(f"/api/batches/{bid}", headers=admin, json={"ou_id": ou("RETAIL").id}).status_code == 422
    r = client.put(f"/api/batches/{bid}", headers=admin,
                   json={"domain_id": domain("IOT").id, "details": {"college": "MEC"}})
    d = r.get_json()["data"]
    assert d["domain"]["name"] == "IoT" and d["details"]["college"] == "MEC" and d["details"]["university"] == "Kerala Uni"


def test_batch_close_and_filter(client, admin):
    bid = client.post("/api/batches", headers=admin, json=batch_body()).get_json()["data"]["id"]
    client.patch(f"/api/batches/{bid}/status", headers=admin, json={"status": "closed"})
    assert client.patch(f"/api/batches/{bid}/status", headers=admin, json={"status": "weird"}).status_code == 422
    r = client.get("/api/batches?status=closed", headers=admin).get_json()
    assert r["meta"]["total"] == 1
    assert client.get("/api/batches?status=active", headers=admin).get_json()["meta"]["total"] == 0


def test_batch_list_scoped_by_role(client, admin, make_user, login):
    mine = client.post("/api/batches", headers=admin, json=batch_body()).get_json()["data"]["code"]
    theirs = client.post("/api/batches", headers=admin, json=batch_body(domain_id=domain("IOT").id)).get_json()["data"]["code"]
    lead = make_user("domain_lead", "lead@x.com")
    client.put(f"/api/domains/{domain('AIML').id}/leads", headers=admin, json={"user_ids": [lead.id]})
    h = login("lead@x.com")
    codes = [b["code"] for b in client.get("/api/batches", headers=h).get_json()["data"]]
    assert codes == [mine]
    other = db.session.query(Batch).filter_by(code=theirs).one().id
    assert client.get(f"/api/batches/{other}", headers=h).status_code == 404
    assert client.post("/api/batches", headers=h, json=batch_body(code="X")).status_code == 403


# ------------------------------------------------------------------------ Users/Staff
def test_create_mentor_generates_profile_and_temp_password(client, admin):
    r = client.post("/api/admin/users", headers=admin,
                    json={"role": "mentor", "name": "Mentor One", "email": "m1@x.com",
                          "domain_id": domain("AIML").id, "designation": "Senior"})
    body = r.get_json()["data"]
    assert r.status_code == 201 and body["temporary_password"] and body["must_change_password"] is True
    mentors = client.get("/api/mentors", headers=admin).get_json()["data"]
    assert mentors[0]["domain"]["name"] == "AI & ML"


def test_cannot_create_student_via_staff_endpoint(client, admin):
    r = client.post("/api/admin/users", headers=admin,
                    json={"role": "student", "name": "S", "email": "s@x.com", "password": "Passw0rd1"})
    assert r.status_code == 422


def test_admin_reset_password_and_self_deactivate_blocked(client, admin, make_user):
    u = make_user("mentor", "m@x.com")
    r = client.post(f"/api/admin/users/{u.id}/reset-password", headers=admin, json={})
    temp = r.get_json()["data"]["temporary_password"]
    assert client.post("/api/auth/login", json={"email": "m@x.com", "password": temp}).status_code == 200
    me = client.get("/api/auth/me", headers=admin).get_json()["data"]["id"]
    assert client.patch(f"/api/admin/users/{me}/active", headers=admin, json={"is_active": False}).status_code == 422


def test_create_single_student(client, admin):
    bid = client.post("/api/batches", headers=admin, json=batch_body()).get_json()["data"]["id"]
    body = {"name": "Stu Dent", "email": "stu@x.com", "registration_no": "R1", "batch_id": bid}
    r = client.post("/api/students", headers=admin, json=body)
    assert r.status_code == 201 and r.get_json()["data"]["temporary_password"]
    assert client.post("/api/students", headers=admin, json={**body, "email": "other@x.com"}).status_code == 409
    assert client.post("/api/students", headers=admin, json={**body, "registration_no": "R2"}).status_code == 409
    listing = client.get(f"/api/students?batch_id={bid}", headers=admin).get_json()
    assert listing["meta"]["total"] == 1
