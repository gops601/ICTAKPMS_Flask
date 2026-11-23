import io

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit, ProblemStatement,
                        Subdomain)


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def people(make_user, login):
    make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id),
                        DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    mu = make_user("mentor", "m@x.com")
    ou = db.session.query(OrganisationalUnit).first()
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    m = Mentor(user_id=mu.id)
    db.session.add_all([batch, m])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m.id))
    db.session.commit()
    return {k: login(f"{e}@x.com") for k, e in (("admin", "admin"), ("la", "la"), ("lb", "lb"), ("m", "m"))}


def add_sub(client, H, dom, name):
    return client.post(f"/api/domains/{domain(dom).id}/subdomains", headers=H, json={"name": name})


def ps(client, H, code, **kw):
    body = {"ps_code": code, "title": f"T{code}", "domain_id": domain("AIML").id, "description": "d", **kw}
    return client.post("/api/problem-statements", headers=H, json=body)


def test_admin_and_own_lead_add_subdomains_others_cannot(client, people):
    assert add_sub(client, people["admin"], "AIML", "Computer Vision").status_code == 201
    assert add_sub(client, people["la"], "AIML", "NLP").status_code == 201
    assert add_sub(client, people["lb"], "AIML", "Robotics").status_code == 404          # other domain's lead
    assert add_sub(client, people["m"], "AIML", "Speech").status_code == 403
    dup = add_sub(client, people["admin"], "AIML", "computer vision")
    assert dup.status_code == 409
    assert add_sub(client, people["admin"], "IOT", "Computer Vision").status_code == 201   # same name, other domain


def test_domain_listing_includes_subdomains_and_mentor_can_read_their_domain(client, people):
    add_sub(client, people["admin"], "AIML", "NLP")
    d = [x for x in client.get("/api/domains", headers=people["admin"]).get_json()["data"] if x["code"] == "AIML"][0]
    assert [s["name"] for s in d["subdomains"]] == ["NLP"]
    assert len(client.get(f"/api/domains/{domain('AIML').id}/subdomains", headers=people["m"]).get_json()["data"]) == 1
    assert client.get(f"/api/domains/{domain('IOT').id}/subdomains", headers=people["m"]).status_code == 404


def test_subdomain_is_required_when_the_domain_has_subdomains(client, people):
    assert ps(client, people["la"], "P0").status_code == 201                       # no subdomains defined yet: optional
    sid = add_sub(client, people["la"], "AIML", "NLP").get_json()["data"]["id"]
    r = ps(client, people["la"], "P1")
    assert r.status_code == 422 and "subdomain_id" in r.get_json()["errors"]
    ok = ps(client, people["la"], "P2", subdomain_id=sid)
    assert ok.status_code == 201 and ok.get_json()["data"]["subdomain"]["name"] == "NLP"


def test_subdomain_must_belong_to_the_chosen_domain_and_be_active(client, people):
    other = add_sub(client, people["admin"], "IOT", "Sensors").get_json()["data"]["id"]
    add_sub(client, people["admin"], "AIML", "NLP")
    assert ps(client, people["la"], "P1", subdomain_id=other).status_code == 422
    sid = add_sub(client, people["admin"], "AIML", "Vision").get_json()["data"]["id"]
    client.patch(f"/api/domains/subdomains/{sid}", headers=people["admin"], json={"is_active": False})
    assert ps(client, people["la"], "P2", subdomain_id=sid).status_code == 422


def test_filter_and_update_by_subdomain(client, people):
    a = add_sub(client, people["la"], "AIML", "NLP").get_json()["data"]["id"]
    b = add_sub(client, people["la"], "AIML", "Vision").get_json()["data"]["id"]
    ps(client, people["la"], "P1", subdomain_id=a)
    ps(client, people["la"], "P2", subdomain_id=b)
    codes = lambda qs: {p["ps_code"] for p in client.get(f"/api/problem-statements{qs}", headers=people["la"]).get_json()["data"]}  # noqa: E731
    assert codes(f"?subdomain_id={a}") == {"P1"} and codes("") == {"P1", "P2"}
    pid = ProblemStatement.query.filter_by(ps_code="P1").one().id
    r = client.put(f"/api/problem-statements/{pid}", headers=people["la"], json={"subdomain_id": b})
    assert r.status_code == 200 and r.get_json()["data"]["subdomain"]["name"] == "Vision"
    assert client.put(f"/api/problem-statements/{pid}", headers=people["la"], json={"title": "Renamed"}).status_code == 200  # keeps subdomain


def test_rename_subdomain(client, people):
    sid = add_sub(client, people["la"], "AIML", "NLP").get_json()["data"]["id"]
    r = client.patch(f"/api/domains/subdomains/{sid}", headers=people["la"], json={"name": "Language AI"})
    assert r.status_code == 200 and r.get_json()["data"]["name"] == "Language AI"
    assert client.patch(f"/api/domains/subdomains/{sid}", headers=people["lb"], json={"name": "x1"}).status_code == 404


def test_bulk_upload_accepts_subdomain_by_name(client, people):
    add_sub(client, people["admin"], "AIML", "NLP")
    header = "Problem Statement ID,Project Title,Domain Code,Description,Subdomain\n"
    good = "BP1,Bulk One,AIML,desc,nlp\n"
    bad_name = "BP2,Bulk Two,AIML,desc,Nope\n"
    missing = "BP3,Bulk Three,AIML,desc,\n"
    r = client.post("/api/imports/problem_statements", headers=people["admin"], content_type="multipart/form-data",
                    data={"file": (io.BytesIO((header + good + bad_name + missing).encode()), "ps.csv")})
    d = r.get_json()["data"]
    assert d["valid_rows"] == 1 and d["error_rows"] == 2
