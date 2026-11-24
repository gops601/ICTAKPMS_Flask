import re
import hashlib
import hmac
import io
import json
import time

import jwt
from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models import Batch, Domain, ExternalPortal, Notification, ProblemStatement, Student, User
from app.services import data_collection
from tests.test_student_shelf import CSV, PDF, domain, world  # noqa: F401


# ============================================================== data-collection sheet
def sheet(rows=None, headers=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data collection"
    ws.append(headers or [c[1] + " *" for c in data_collection.COLUMNS])
    for r in rows if rows is not None else [[c[5] for c in data_collection.COLUMNS]]:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def post(client, world, sheet_file=None, datasets=True, **extra):
    data = {"title": "Attendance", "summary": "s", "file": (io.BytesIO(PDF), "p.pdf")}
    if datasets:
        data["datasets"] = [(io.BytesIO(CSV), "d.csv")]
    if sheet_file is not None:
        data["data_sheet"] = (sheet_file, "sheet.xlsx")
    data.update(extra)
    return client.post("/api/proposals", headers=world["H"]["s1"], data=data, content_type="multipart/form-data")


def test_template_download_is_a_valid_workbook_with_example_and_instructions(client, world):   # noqa: F811
    r = client.get("/api/proposals/data-template", headers=world["H"]["s1"])
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype and "attachment" in r.headers["Content-Disposition"]
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["Data collection", "Example", "Instructions"]
    assert [c.value for c in wb["Data collection"][1]][0] == "Dataset Name *"
    assert wb["Example"].max_row == 2
    assert client.get("/api/proposals/data-template").status_code == 401


def test_datasets_need_the_filled_sheet_and_it_is_stored_on_the_proposal_and_shelf(client, world):   # noqa: F811
    r = post(client, world)                                              # datasets, no sheet
    assert r.status_code == 422 and "data_sheet" in r.get_json()["errors"]
    r = post(client, world, sheet())
    assert r.status_code == 201, r.get_json()
    d = r.get_json()["data"]
    assert len(d["data_collection"]) == 1 and d["data_collection"][0]["name"] == "Student attendance records"
    assert d["data_collection"][0]["records"] == 12000 and d["data_collection"][0]["personal_data"] == "Yes"
    assert len(d["datasets"]) == 2                                       # the dataset + the sheet itself
    ps = db.session.get(ProblemStatement, d["shelf"]["id"])
    assert ps.data_collection[0]["file_format"] == "CSV"
    shown = client.get(f"/api/problem-statements/{ps.id}", headers=world["H"]["lead"]).get_json()["data"]
    assert shown["data_collection"][0]["feature_names"].startswith("student_id")


def test_sheet_alone_is_fine_and_no_sheet_no_datasets_is_unchanged(client, world):   # noqa: F811
    assert post(client, world, sheet(), datasets=False).status_code == 201


def test_bad_sheet_rows_are_reported_with_row_numbers(client, world):           # noqa: F811
    good = [c[5] for c in data_collection.COLUMNS]
    bad = list(good)
    bad[0], bad[6], bad[2], bad[13] = None, "many", "Telepathy", "Maybe"
    r = post(client, world, sheet([good, bad]))
    msg = r.get_json()["message"]
    assert r.status_code == 422 and "Row 3: Dataset Name is required" in msg and "Row 3: Number of Records must be a whole number" in msg
    assert "Source must be one of" in msg and "Contains Personal Data must be one of" in msg and "Row 2" not in msg
    assert post(client, world, sheet([])).status_code == 422                             # no rows
    assert post(client, world, sheet(headers=["Only", "Two"], rows=[["a", "b"]])).status_code == 422   # wrong template
    r = client.post("/api/proposals", headers=world["H"]["s1"], content_type="multipart/form-data",
                    data={"title": "T", "file": (io.BytesIO(PDF), "p.pdf"), "data_sheet": (io.BytesIO(b"x"), "sheet.csv")})
    assert r.status_code == 422


# ============================================================== external portals: SSO + enrolment
def make_portal(client, world, **kw):
    r = client.post("/api/admin/portals", headers=world["H"]["admin"], json={"name": "ICTAK Learn", **kw})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def signed(secret, **claims):
    return jwt.encode({"exp": int(time.time()) + 120, **claims}, secret, algorithm="HS256")


def push(client, portal, payload, secret=None):
    raw = json.dumps(payload).encode()
    sig = hmac.new((secret or portal["shared_secret"]).encode(), raw, hashlib.sha256).hexdigest()
    return client.post(f"/api/integrations/{portal['slug']}/enrollments", data=raw, content_type="application/json",
                       headers={"X-Signature": f"sha256={sig}"})


PAYLOAD = {"batches": [{"code": "EXT-1", "name": "Jan cohort", "domain": "AIML", "start_date": "2026-01-05", "details": {"programme_name": "P"},
                        "students": [{"name": "Asha K", "email": "asha@ext.com", "registration_no": "R1"},
                                     {"name": "Ben J", "email": "ben@ext.com"}]}]}


def test_admin_manages_portals_and_the_secret_is_shown_once(client, world):      # noqa: F811
    p = make_portal(client, world, base_url="https://learn.example.org", api_token="tok")
    assert p["slug"] == "ictak-learn" and len(p["shared_secret"]) > 20 and p["has_api_token"] is True
    assert "api_token" not in p and p["push_endpoint"].endswith("/api/integrations/ictak-learn/enrollments")
    listed = client.get("/api/admin/portals", headers=world["H"]["admin"]).get_json()["data"]
    assert len(listed) == 1 and "shared_secret" not in listed[0]
    assert make_portal(client, world)["slug"] == "ictak-learn-2"
    for who in ("lead", "m1", "s1"):
        assert client.get("/api/admin/portals", headers=world["H"][who]).status_code == 403
    r = client.post(f"/api/admin/portals/{p['id']}/rotate-secret", headers=world["H"]["admin"])
    assert r.get_json()["data"]["shared_secret"] != p["shared_secret"]
    assert client.put(f"/api/admin/portals/{p['id']}", headers=world["H"]["admin"], json={"name": "Renamed"}).get_json()["data"]["has_api_token"] is True
    assert client.delete(f"/api/admin/portals/{p['id']}", headers=world["H"]["admin"]).status_code == 200


def test_push_enrols_batches_and_students_idempotently(client, world):           # noqa: F811
    from app.services.domain_sync_service import ensure_lead_mentor_profile
    ensure_lead_mentor_profile(db.session.query(User).filter_by(email="lead@x.com").one(), db.session.query(Domain).filter_by(code="AIML").one().id)
    p = make_portal(client, world)
    db.session.query(Notification).delete()
    db.session.commit()
    r = push(client, p, PAYLOAD)
    s = r.get_json()["data"]
    assert r.status_code == 200 and (s["batches_created"], s["students_created"], s["problems"]) == (1, 2, [])
    batch = db.session.query(Batch).filter_by(external_ref="EXT-1").one()
    assert re.fullmatch(r"[A-Z]+_ONLINE_0001", batch.code) and batch.domain.code == "AIML" and str(batch.start_date) == "2026-01-05"
    assert db.session.query(Student).filter_by(batch_id=batch.id).count() == 2
    assert db.session.query(Notification).filter_by(type="batch_assigned").count() >= 1       # the domain lead hears about it
    assert {m.mentor.user.email for m in batch.batch_mentors} == {"lead@x.com"}                # only the domain lead joins by default
    again = push(client, p, PAYLOAD).get_json()["data"]
    assert (again["batches_created"], again["students_created"], again["batches_updated"], again["students_updated"]) == (0, 0, 1, 2)
    assert db.session.query(Batch).filter_by(external_ref="EXT-1").count() == 1
    assert db.session.get(ExternalPortal, p["id"]).last_sync_summary["students_created"] == 0


def test_required_text_fields_of_the_ou_are_filled_in_automatically(client, world):   # noqa: F811
    p = make_portal(client, world)
    payload = {"batches": [{"code": "Z", "name": "No details", "domain": "AIML"}]}
    assert push(client, p, payload).get_json()["data"]["batches_created"] == 1
    assert db.session.query(Batch).filter_by(external_ref="Z").one().ou_details[0].value == "Imported from ICTAK Learn"


def test_push_reports_problems_without_stopping(client, world):                  # noqa: F811
    p = make_portal(client, world)
    payload = {"batches": [{"code": "X", "name": "Bad domain", "domain": "NOPE", "students": []},
                           {"code": "Y", "name": "Ok", "domain": "IOT", "details": {"programme_name": "P"}, "students": [{"name": "S1 dup", "email": "s1@x.com"}, {"name": "", "email": "bad"}]},
                           {"name": "no code"}]}
    s = push(client, p, payload).get_json()["data"]
    assert s["batches_created"] == 1 and s["students_created"] == 0 and len(s["problems"]) == 4
    assert any("domain 'NOPE'" in m for m in s["problems"]) and any("already enrolled in batch B1" in m for m in s["problems"])
    assert db.session.query(Batch).filter_by(external_ref="X").count() == 0


def test_push_needs_a_valid_signature(client, world):                            # noqa: F811
    p = make_portal(client, world)
    assert push(client, p, PAYLOAD, secret="wrong").status_code == 401
    assert client.post(f"/api/integrations/{p['slug']}/enrollments", json=PAYLOAD).status_code == 401
    assert client.post("/api/integrations/nope/enrollments", json=PAYLOAD).status_code == 401
    client.put(f"/api/admin/portals/{p['id']}", headers=world["H"]["admin"], json={"is_active": False})
    assert push(client, p, PAYLOAD).status_code == 401


def test_sso_signs_in_an_enrolled_student(client, world):                        # noqa: F811
    p = make_portal(client, world)
    push(client, p, PAYLOAD)
    r = client.post("/api/auth/sso", json={"portal": p["slug"], "token": signed(p["shared_secret"], email="Asha@ext.com")})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["user"]["role"] == "student" and d["user"]["email"] == "asha@ext.com"
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + d["access_token"]})
    assert me.status_code == 200 and me.get_json()["data"]["email"] == "asha@ext.com"


def test_sso_enrols_a_new_student_just_in_time_only_into_a_known_batch(client, world):   # noqa: F811
    p = make_portal(client, world)
    push(client, p, PAYLOAD)
    tok = lambda **c: client.post("/api/auth/sso", json={"portal": p["slug"], "token": signed(p["shared_secret"], **c)})   # noqa: E731
    assert tok(email="new@ext.com").status_code == 403                                  # unknown, no batch claim
    assert tok(email="new@ext.com", name="New Kid", batch="NOPE").status_code == 403
    r = tok(email="new@ext.com", name="New Kid", batch="EXT-1", reg_no="R9")
    assert r.status_code == 200 and db.session.query(Student).filter_by(registration_no="R9").count() == 1


def test_sso_rejects_bad_tokens_admins_and_inactive_users(client, world):        # noqa: F811
    p = make_portal(client, world)
    push(client, p, PAYLOAD)
    go = lambda token, slug=None: client.post("/api/auth/sso", json={"portal": slug or p["slug"], "token": token})   # noqa: E731
    assert go(signed("wrong-secret", email="asha@ext.com")).status_code == 401
    assert go(jwt.encode({"email": "asha@ext.com", "exp": int(time.time()) - 5}, p["shared_secret"], algorithm="HS256")).status_code == 401   # expired
    assert go(jwt.encode({"email": "asha@ext.com", "exp": int(time.time()) + 86400}, p["shared_secret"], algorithm="HS256")).status_code == 401   # too long-lived
    assert go(jwt.encode({"email": "asha@ext.com"}, p["shared_secret"], algorithm="HS256")).status_code == 401                                  # no exp
    assert go(signed(p["shared_secret"], email="asha@ext.com", iss="someone-else")).status_code == 401
    assert go(signed(p["shared_secret"], email="asha@ext.com"), slug="nope").status_code == 401
    assert go(signed(p["shared_secret"], email="admin@x.com")).status_code == 403
    u = db.session.query(User).filter_by(email="asha@ext.com").one()
    u.is_active = False
    db.session.commit()
    assert go(signed(p["shared_secret"], email="asha@ext.com")).status_code == 403


def test_pull_sync_reads_the_portals_feed(client, world, monkeypatch):           # noqa: F811
    p = make_portal(client, world, base_url="https://learn.example.org", api_token="tok")
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return json.dumps(PAYLOAD).encode()

    def fake_open(req, timeout=0):
        seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
        return Resp()
    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    r = client.post(f"/api/admin/portals/{p['id']}/sync", headers=world["H"]["admin"])
    assert r.status_code == 200 and r.get_json()["data"]["last_sync_summary"]["students_created"] == 2
    assert seen == {"url": "https://learn.example.org/api/enrollments", "auth": "Bearer tok"}
    assert client.post(f"/api/admin/portals/{p['id']}/sync", headers=world["H"]["lead"]).status_code == 403
    no_url = make_portal(client, world, name="Pushonly")
    assert client.post(f"/api/admin/portals/{no_url['id']}/sync", headers=world["H"]["admin"]).status_code == 422


# ============================================================== documentation + configuration file
def test_configuration_file_and_guide_download_for_admins_only(client, world):   # noqa: F811
    p = make_portal(client, world)
    r = client.get(f"/api/admin/portals/{p['id']}/config", headers=world["H"]["admin"])
    cfg = json.loads(r.data)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and r.headers["Content-Disposition"].endswith('-ictak-config.json"')
    assert cfg["portal"]["id"] == "ictak-learn" and cfg["ictak"]["enrollment_push_endpoint"].endswith("/api/integrations/ictak-learn/enrollments")
    assert cfg["auth"]["sso_token"]["algorithm"] == "HS256" and cfg["auth"]["sso_token"]["max_lifetime_seconds"] == 600
    assert p["shared_secret"] not in r.get_data(as_text=True)                        # the real secret is never in the file
    env = client.get(f"/api/admin/portals/{p['id']}/config?format=env", headers=world["H"]["admin"]).get_data(as_text=True)
    assert "ICTAK_PORTAL_ID=ictak-learn" in env and "ICTAK_SHARED_SECRET=<PASTE_SHARED_SECRET_HERE>" in env and p["shared_secret"] not in env
    g = client.get("/api/admin/portals/integration-guide", headers=world["H"]["admin"])
    assert g.status_code == 200 and "X-Signature" in g.get_data(as_text=True) and "/sso?portal=" in g.get_data(as_text=True)
    for who in ("lead", "m1", "s1"):
        assert client.get(f"/api/admin/portals/{p['id']}/config", headers=world["H"][who]).status_code == 403
        assert client.get("/api/admin/portals/integration-guide", headers=world["H"][who]).status_code == 403
    assert client.get("/api/admin/portals/999/config", headers=world["H"]["admin"]).status_code == 404


def test_students_get_the_same_project_template_as_the_project_shelf(client, world):   # noqa: F811
    r = client.get("/api/proposals/project-template", headers=world["H"]["s1"])
    shelf = client.get("/api/problem-statements/template", headers=world["H"]["lead"])
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype
    mine, theirs = load_workbook(io.BytesIO(r.data)), load_workbook(io.BytesIO(shelf.data))
    assert [c.value for c in mine["Data"][1]] == [c.value for c in theirs["Data"][1]] and "Project Title" in [c.value for c in mine["Data"][1]]
    csv = client.get("/api/proposals/project-template?format=csv", headers=world["H"]["s1"])
    assert csv.status_code == 200 and b"Project Title" in csv.data
    assert client.get("/api/proposals/project-template?format=pdf", headers=world["H"]["s1"]).status_code == 422
    assert client.get("/api/proposals/project-template").status_code == 401
