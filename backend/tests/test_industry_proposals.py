import io

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit, ProblemStatement,
                        Project, ProjectStudent, Student)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    lead = make_user("domain_lead", "lead@x.com")
    db.session.add(DomainLead(user_id=lead.id, domain_id=domain("AIML").id))
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    mu, ou_ = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com")
    m1, m2 = Mentor(user_id=mu.id), Mentor(user_id=ou_.id)  # m2 is not on the batch
    db.session.add_all([m1, m2])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    studs = {}
    for n in ("s1", "s2"):
        u = make_user("student", f"{n}@x.com")
        db.session.flush()
        studs[n] = Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper())
        db.session.add(studs[n])
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "lead", "m1", "m2", "s1", "s2")}
    return dict(H=H, batch=batch, studs=studs)


# ------------------------------------------------------------ mentor types
def create_mentor(client, headers, **kw):
    body = {"role": "mentor", "name": "Ind Mentor", "email": "ind@x.com", **kw}
    return client.post("/api/admin/users", headers=headers, json=body)


def test_mentor_defaults_to_internal(client, world):
    r = create_mentor(client, world["H"]["admin"])
    assert r.status_code == 201
    mentors = client.get("/api/mentors", headers=world["H"]["admin"]).get_json()["data"]
    assert {m["mentor_type"] for m in mentors} == {"internal"}


def test_industry_mentor_requires_details_and_profile(client, world):
    r = create_mentor(client, world["H"]["admin"], mentor_type="industry")
    assert r.status_code == 422
    errs = r.get_json()["errors"]
    assert {"company", "industry_sector", "designation", "bio"} <= set(errs)


def test_industry_mentor_saved_and_filterable(client, world):
    H = world["H"]["admin"]
    r = create_mentor(client, H, mentor_type="industry", company="Acme", industry_sector="Healthcare",
                      designation="CTO", experience_years=12, bio="Built things.",
                      linkedin_url="https://linkedin.com/in/x")
    assert r.status_code == 201, r.get_json()
    ind = client.get("/api/mentors?mentor_type=industry", headers=H).get_json()["data"]
    assert len(ind) == 1 and ind[0]["company"] == "Acme" and ind[0]["experience_years"] == 12
    assert len(client.get("/api/mentors?mentor_type=internal", headers=H).get_json()["data"]) == 2


def test_internal_mentor_drops_industry_fields(client, world):
    H = world["H"]["admin"]
    create_mentor(client, H, mentor_type="internal", company="Ignored", bio="x")
    m = [m for m in client.get("/api/mentors", headers=H).get_json()["data"] if m["email"] == "ind@x.com"][0]
    assert m["company"] is None and m["bio"] is None


def test_bad_profile_link_rejected(client, world):
    r = create_mentor(client, world["H"]["admin"], mentor_type="industry", company="A", industry_sector="B",
                      designation="C", bio="D", linkedin_url="javascript:alert(1)")
    assert r.status_code == 422


# -------------------------------------------------- problem statement source
def ps(client, headers, code, **kw):
    body = {"ps_code": code, "title": f"T {code}", "domain_id": domain("AIML").id, "description": "d", **kw}
    return client.post("/api/problem-statements", headers=headers, json=body)


def test_industry_statement_requires_industry(client, world):
    r = ps(client, world["H"]["lead"], "P1", source_type="industry")
    assert r.status_code == 422 and "industry" in r.get_json()["errors"]


def test_statement_type_defaults_internal_and_clears_industry(client, world):
    H = world["H"]["lead"]
    d = ps(client, H, "P1", industry="Ignored").get_json()["data"]
    assert d["source_type"] == "internal" and d["industry"] is None


def test_industry_filter_and_list(client, world):
    H = world["H"]["lead"]
    ps(client, H, "P1", source_type="industry", industry="Healthcare")
    ps(client, H, "P2", source_type="industry", industry="Finance")
    ps(client, H, "P3")
    codes = lambda qs: {p["ps_code"] for p in client.get(f"/api/problem-statements{qs}", headers=H).get_json()["data"]}  # noqa: E731
    assert codes("?industry=healthcare") == {"P1"}
    assert codes("?source_type=industry") == {"P1", "P2"}
    assert codes("?source_type=internal") == {"P3"}
    assert client.get("/api/problem-statements/industries", headers=H).get_json()["data"] == ["Finance", "Healthcare"]


# ---------------------------------------------------------------- proposals
def propose(client, world, who="s1", title="My idea", content=PDF, name="idea.pdf"):
    return client.post("/api/proposals", headers=world["H"][who], content_type="multipart/form-data",
                       data={"title": title, "summary": "s", "file": (io.BytesIO(content), name)})


def test_student_can_upload_and_mentor_approves(client, world):
    r = propose(client, world)
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["data"]["id"]
    assert client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]["can_upload"] is False
    # another student cannot see it; unrelated mentor cannot review; reviewing mentor can
    assert client.get("/api/proposals", headers=world["H"]["s2"]).get_json()["data"] == []
    assert client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m2"], json={"decision": "approve"}).status_code == 404
    ok_ = client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"], json={"decision": "approve"})
    assert ok_.status_code == 200 and ok_.get_json()["data"]["status"] == "approved"
    assert client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"], json={"decision": "approve"}).status_code == 409
    assert client.get(f"/api/proposals/{pid}/download", headers=world["H"]["s1"]).data == PDF


def test_rejection_needs_remarks_and_allows_resubmission(client, world):
    pid = propose(client, world).get_json()["data"]["id"]
    assert client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"], json={"decision": "reject"}).status_code == 422
    assert client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"],
                       json={"decision": "reject", "remarks": "Too vague"}).status_code == 200
    assert client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]["can_upload"] is True
    assert propose(client, world, title="Better").status_code == 201


def test_second_open_proposal_blocked(client, world):
    assert propose(client, world).status_code == 201
    assert propose(client, world, title="Again").status_code == 409


def test_upload_blocked_once_project_allocated(client, world):
    s = world["studs"]["s1"]
    ps_ = ProblemStatement(ps_code="X", title="X", domain_id=domain("AIML").id, description="d")
    db.session.add(ps_)
    db.session.flush()
    p = Project(batch_id=world["batch"].id, problem_statement_id=ps_.id, title="P")
    db.session.add(p)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=p.id, student_id=s.id))
    db.session.commit()
    info = client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]
    assert info["can_upload"] is False and info["has_project"] is True
    assert propose(client, world).status_code == 409


def test_allocation_withdraws_pending_proposal(client, world):
    propose(client, world)
    ps_ = ProblemStatement(ps_code="X", title="X", domain_id=domain("AIML").id, description="d")
    db.session.add(ps_)
    db.session.commit()
    r = client.post("/api/project-allocation", headers=world["H"]["lead"], json={
        "batch_id": world["batch"].id, "mentor_id": None, "start_date": None,
        "items": [{"problem_statement_id": ps_.id, "student_ids": [world["studs"]["s1"].id], "team": False}]})
    assert r.status_code == 201, r.get_json()
    mine = client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]
    assert mine["proposals"][0]["status"] == "withdrawn"


def test_only_students_upload_and_only_mentors_review(client, world):
    r = client.post("/api/proposals", headers=world["H"]["m1"], content_type="multipart/form-data",
                    data={"title": "t", "file": (io.BytesIO(PDF), "a.pdf")})
    assert r.status_code == 403
    pid = propose(client, world).get_json()["data"]["id"]
    for who in ("admin", "lead", "s1"):
        assert client.post(f"/api/proposals/{pid}/review", headers=world["H"][who],
                           json={"decision": "approve"}).status_code == 403
    assert len(client.get("/api/proposals", headers=world["H"]["lead"]).get_json()["data"]) == 1  # read-only visibility


# ------------------------------------------------------- batch project dates
def test_lead_notified_on_batch_creation_and_sets_project_dates(client, world):
    from app.models import Notification
    ou = db.session.query(OrganisationalUnit).first()
    r = client.post("/api/batches", headers=world["H"]["admin"],
                    json={"code": "B2", "name": "Second", "ou_id": ou.id, "domain_id": domain("AIML").id,
                          "details": {"programme_name": "P"}})
    assert r.status_code == 201, r.get_json()
    bid = r.get_json()["data"]["id"]
    n = db.session.query(Notification).filter_by(type="batch_assigned").one()
    assert "project start and end dates" in n.message and n.link == f"/lead/batches/{bid}"

    L = world["H"]["lead"]
    bad = client.put(f"/api/batches/{bid}/project-dates", headers=L,
                     json={"project_start_date": "2026-12-10", "project_end_date": "2026-12-01"})
    assert bad.status_code == 422
    good = client.put(f"/api/batches/{bid}/project-dates", headers=L,
                      json={"project_start_date": "2026-12-01", "project_end_date": "2027-02-01"})
    assert good.status_code == 200 and good.get_json()["data"]["project_end_date"] == "2027-02-01"
    # mentors/students cannot set them
    for who in ("m1", "s1"):
        assert client.put(f"/api/batches/{bid}/project-dates", headers=world["H"][who],
                          json={"project_start_date": "2026-12-01", "project_end_date": "2027-02-01"}).status_code == 403


def test_allocation_uses_batch_project_dates(client, world):
    L = world["H"]["lead"]
    bid = world["batch"].id
    client.put(f"/api/batches/{bid}/project-dates", headers=L,
               json={"project_start_date": "2026-12-01", "project_end_date": "2027-02-01"})
    ps_ = ProblemStatement(ps_code="X", title="X", domain_id=domain("AIML").id, description="d")
    db.session.add(ps_)
    db.session.commit()
    r = client.post("/api/project-allocation", headers=L, json={
        "batch_id": bid, "mentor_id": None, "start_date": None,
        "items": [{"problem_statement_id": ps_.id, "student_ids": [world["studs"]["s1"].id], "team": False}]})
    assert r.status_code == 201, r.get_json()
    p = db.session.query(Project).one()
    assert p.start_date.isoformat() == "2026-12-01" and p.target_end_date.isoformat() == "2027-02-01"
