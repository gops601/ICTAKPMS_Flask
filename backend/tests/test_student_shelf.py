import io
import re

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, Notification, OrganisationalUnit, Project,
                        ProblemStatement, ProjectStudent, ProposalDataset, Student, Subdomain, User)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"
CSV = b"a,b\n1,2\n"


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
    mu = make_user("mentor", "m1@x.com")
    m1 = Mentor(user_id=mu.id, domain_id=domain("AIML").id)
    iot_u, free_u = make_user("mentor", "iot@x.com"), make_user("mentor", "free@x.com")
    iot = Mentor(user_id=iot_u.id, domain_id=domain("IOT").id)
    free = Mentor(user_id=free_u.id, domain_id=None)
    db.session.add_all([m1, iot, free])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    su = make_user("student", "s1@x.com")
    db.session.flush()
    student = Student(user_id=su.id, batch_id=batch.id, registration_no="S1")
    db.session.add(student)
    db.session.commit()
    H = {k: login(f"{e}@x.com") for k, e in (("admin", "admin"), ("lead", "lead"), ("m1", "m1"), ("s1", "s1"))}
    return dict(H=H, batch=batch, student=student, mentor_user=mu)


# ------------------------------------------------ domain lead is created with a domain
def create_lead(client, H, **kw):
    return client.post("/api/admin/users", headers=H, json={"role": "domain_lead", "name": "New Lead", "email": "nl@x.com", **kw})


def test_domain_lead_must_be_created_with_a_domain(client, world):
    H = world["H"]["admin"]
    r = create_lead(client, H)
    assert r.status_code == 422 and "domain_ids" in r.get_json()["errors"]
    assert db.session.query(User).filter_by(email="nl@x.com").count() == 0            # nothing half-created
    assert create_lead(client, H, domain_ids=[99999]).status_code == 422
    ok = create_lead(client, H, domain_ids=[domain("AIML").id, domain("IOT").id])
    assert ok.status_code == 201, ok.get_json()
    uid = ok.get_json()["data"]["id"]
    assert {l.domain_id for l in db.session.query(DomainLead).filter_by(user_id=uid)} == {domain("AIML").id, domain("IOT").id}
    domain("IOT").is_active = False
    db.session.commit()
    r = client.post("/api/admin/users", headers=H, json={"role": "domain_lead", "name": "X", "email": "x2@x.com", "domain_ids": [domain("IOT").id]})
    assert r.status_code == 422                                                       # inactive domain


# ------------------------------------------------ mentors under the domain
def test_mentor_picker_offers_domain_mentors_plus_unassigned(client, world):
    H = world["H"]["lead"]
    names = {m["email"] for m in client.get(f"/api/mentors?for_domain={domain('AIML').id}", headers=H).get_json()["data"]}
    assert names == {"m1@x.com", "free@x.com"}                                        # IoT mentor is not offered for an AIML batch
    other = client.post(f"/api/batches/{world['batch'].id}/mentors", headers=H,
                        json={"mentor_id": db.session.query(Mentor).join(User).filter(User.email == "iot@x.com").one().id})
    assert other.status_code == 422                                                   # and the server refuses it too


def test_a_batch_can_have_several_mentors_who_can_allocate(client, world):
    H = world["H"]["lead"]
    free = db.session.query(Mentor).join(User).filter(User.email == "free@x.com").one()
    assert client.post(f"/api/batches/{world['batch'].id}/mentors", headers=H, json={"mentor_id": free.id}).status_code == 201
    assert len(client.get(f"/api/batches/{world['batch'].id}/mentors", headers=H).get_json()["data"]) == 2


# ------------------------------------------------ student project -> project shelf
def upload(client, world, title="Crop Disease Detector", datasets=2, subdomain_id=None):
    data = {"title": title, "summary": "Detect crop disease from leaf photos", "file": (io.BytesIO(PDF), "detail.pdf")}
    if subdomain_id:
        data["subdomain_id"] = str(subdomain_id)
    data["datasets"] = [(io.BytesIO(CSV), f"data{i}.csv") for i in range(datasets)]
    if datasets:        # datasets must be described in the data-collection sheet
        from app.services import data_collection
        from tests.test_portals_datasheet import sheet
        data["data_sheet"] = (sheet(), "sheet.xlsx")
    return client.post("/api/proposals", headers=world["H"]["s1"], content_type="multipart/form-data", data=data)


def test_student_project_goes_onto_the_shelf_at_once_and_mentor_approval_starts_the_project(client, world):
    db.session.query(Notification).delete()
    db.session.commit()
    r = upload(client, world)
    assert r.status_code == 201, r.get_json()
    d = r.get_json()["data"]
    assert [x["name"] for x in d["datasets"]] == ["data0.csv", "data1.csv", "sheet.xlsx"] and re.fullmatch(r"ICT_PS_[A-Z2-9]{6}", d["shelf"]["ps_code"])
    pid = d["id"]
    # on the lead's shelf immediately, but pending: not allocatable, no project yet, so no SRS
    items = client.get("/api/problem-statements", headers=world["H"]["lead"]).get_json()["data"]
    assert [i["title"] for i in items] == ["Crop Disease Detector"] and items[0]["approval_status"] == "pending"
    det = client.get(f"/api/problem-statements/{items[0]['id']}", headers=world["H"]["lead"]).get_json()["data"]
    assert det["proposed_by"]["name"] == world["student"].user.name and det["domain"]["name"] == "AI & ML"
    assert len(det["datasets"]) == 3 and len(det["documents"]) == 1 and "leaf photos" in det["description"]
    assert client.get("/api/projects", headers=world["H"]["s1"]).get_json()["data"] == []
    assert db.session.query(Notification).filter_by(type="shelf_student_project").count() == 1       # lead told at submission
    assert db.session.query(Notification).filter_by(type="proposal_submitted").count() == 1          # mentor told too
    r = client.post("/api/project-allocation", headers=world["H"]["lead"], json={"batch_id": world["batch"].id, "mentor_id": None, "start_date": None,
                    "items": [{"problem_statement_id": items[0]["id"], "student_ids": [world["student"].id], "team": False}]})
    assert r.status_code == 422 and "not been approved" in r.get_json()["message"]
    # mentor approves -> shelf entry approved AND the student's project starts with that mentor
    a = client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"], json={"decision": "approve"})
    assert a.status_code == 200
    det = client.get(f"/api/problem-statements/{items[0]['id']}", headers=world["H"]["lead"]).get_json()["data"]
    assert det["approval_status"] == "approved"
    projects = client.get("/api/projects", headers=world["H"]["s1"]).get_json()["data"]
    assert len(projects) == 1 and projects[0]["problem_statement"]["ps_code"] == items[0]["ps_code"] and projects[0]["stage"] == "srs_preparation"
    assert projects[0]["mentors"][0]["name"] == world["mentor_user"].name
    assert items[0]["ps_code"] in db.session.query(Notification).filter_by(type="proposal_reviewed").one().message
    assert client.get(f"/api/problem-statements/{det['id']}/datasets/{det['datasets'][0]['id']}/download", headers=world["H"]["lead"]).data == CSV


def test_srs_only_starts_after_the_mentor_approved_the_problem(client, world):
    upload(client, world)
    ps = db.session.query(ProblemStatement).one()
    # force-allocate the pending problem (as if someone bypassed the API) and check the SRS gates still hold
    p = Project(batch_id=world["batch"].id, problem_statement_id=ps.id, title=ps.title, stage="allocated")
    db.session.add(p)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=p.id, student_id=world["student"].id))
    db.session.commit()
    r = client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["s1"], json={"to": "srs_preparation"})
    assert r.status_code == 409 and "approved the problem statement" in r.get_json()["message"]
    ps.approval_status = "approved"
    db.session.commit()
    assert client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["s1"], json={"to": "srs_preparation"}).status_code == 200


def test_rejected_projects_stay_off_the_active_shelf(client, world):
    pid = upload(client, world).get_json()["data"]["id"]
    client.post(f"/api/proposals/{pid}/review", headers=world["H"]["m1"], json={"decision": "reject", "remarks": "Too broad"})
    ps = db.session.query(ProblemStatement).one()
    assert ps.approval_status == "rejected" and ps.status == "inactive"
    assert client.get("/api/projects", headers=world["H"]["s1"]).get_json()["data"] == []
    assert client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]["can_upload"] is True   # may try again


def test_shelf_can_be_filtered_by_approval_status(client, world):
    upload(client, world)
    mk = ProblemStatement(ps_code="STAFF1", title="Staff", domain_id=domain("AIML").id, description="d")
    db.session.add(mk)
    db.session.commit()
    codes = lambda qs: {x["ps_code"] for x in client.get(f"/api/problem-statements{qs}", headers=world["H"]["lead"]).get_json()["data"]}  # noqa: E731
    assert codes("?approval_status=approved") == {"STAFF1"} and len(codes("?approval_status=pending")) == 1 and len(codes("")) == 2


def test_subdomain_is_required_when_the_domain_has_one_and_must_belong_to_it(client, world):
    sd = Subdomain(domain_id=domain("AIML").id, name="Vision")
    other = Subdomain(domain_id=domain("IOT").id, name="Sensors")
    db.session.add_all([sd, other])
    db.session.commit()
    info = client.get("/api/proposals/mine", headers=world["H"]["s1"]).get_json()["data"]
    assert info["domain"]["name"] == "AI & ML" and [s["name"] for s in info["subdomains"]] == ["Vision"]
    assert upload(client, world).status_code == 422
    assert upload(client, world, subdomain_id=other.id).status_code == 422
    ok = upload(client, world, subdomain_id=sd.id)
    assert ok.status_code == 201
    assert db.session.query(ProblemStatement).one().subdomain_id == sd.id


def test_too_many_datasets_are_refused(client, world):
    assert upload(client, world, datasets=11).status_code == 422
    assert db.session.query(ProposalDataset).count() == 0


def test_proposal_dataset_download_is_scoped(client, world, make_user, login):
    pid = upload(client, world).get_json()["data"]["id"]
    ds = db.session.query(ProposalDataset).first()
    assert client.get(f"/api/proposals/{pid}/datasets/{ds.id}/download", headers=world["H"]["m1"]).data == CSV
    make_user("student", "other@x.com")
    assert client.get(f"/api/proposals/{pid}/datasets/{ds.id}/download", headers=login("other@x.com")).status_code in (403, 404)


def test_deleting_a_shelf_entry_keeps_files_the_proposal_still_uses(client, world):
    pid = upload(client, world).get_json()["data"]["id"]
    ps = db.session.query(ProblemStatement).one()
    assert client.delete(f"/api/problem-statements/{ps.id}", headers=world["H"]["lead"]).status_code == 200
    assert db.session.query(ProblemStatement).count() == 0
    mine = client.get(f"/api/proposals/{pid}/datasets/{db.session.query(ProposalDataset).first().id}/download", headers=world["H"]["s1"])
    assert mine.status_code == 200 and mine.data == CSV                                 # student's own copy of the files survives


def test_deleting_a_pending_student_account_removes_proposal_but_not_the_shelf_entry(client, world):
    upload(client, world)
    r = client.delete(f"/api/admin/users/{world['student'].user_id}", headers=world["H"]["admin"])
    assert r.status_code == 200, r.get_json()
    ps = db.session.query(ProblemStatement).one()
    db.session.refresh(ps)
    assert len(ps.datasets) == 3 and len(ps.documents) == 1 and ps.proposed_by_student_id is None   # the shelf keeps its files


def test_other_allocation_withdraws_the_pending_shelf_entry(client, world):
    upload(client, world)
    staff = ProblemStatement(ps_code="STAFF1", title="Staff", domain_id=domain("AIML").id, description="d")
    db.session.add(staff)
    db.session.commit()
    r = client.post("/api/project-allocation", headers=world["H"]["lead"], json={"batch_id": world["batch"].id, "mentor_id": None, "start_date": None,
                    "items": [{"problem_statement_id": staff.id, "student_ids": [world["student"].id], "team": False}]})
    assert r.status_code == 201
    mine = db.session.query(ProblemStatement).filter(ProblemStatement.ps_code != "STAFF1").one()
    assert mine.approval_status == "withdrawn" and mine.status == "inactive"


# ---------------------------------------------------- everything stays in sync across the domain
def test_new_mentor_in_a_domain_is_visible_to_and_announced_to_the_domain_lead(client, world):
    db.session.query(Notification).delete()
    db.session.commit()
    r = client.post("/api/admin/users", headers=world["H"]["admin"], json={"role": "mentor", "name": "Newbie", "email": "newbie@x.com", "domain_id": domain("AIML").id})
    assert r.status_code == 201
    assert "newbie@x.com" in {m["email"] for m in client.get("/api/mentors", headers=world["H"]["lead"]).get_json()["data"]}
    assert db.session.query(Notification).filter_by(type="mentor_added").count() == 1
    other = client.post("/api/admin/users", headers=world["H"]["admin"], json={"role": "mentor", "name": "IoT M", "email": "iotm@x.com", "domain_id": domain("IOT").id})
    assert other.status_code == 201
    assert "iotm@x.com" not in {m["email"] for m in client.get("/api/mentors", headers=world["H"]["lead"]).get_json()["data"]}   # other domain's mentor


def test_batch_and_shelf_entry_created_by_admin_reach_the_domains_lead_and_mentors(client, world):
    ou = db.session.query(OrganisationalUnit).first()
    db.session.query(Notification).delete()
    db.session.commit()
    b = client.post("/api/batches", headers=world["H"]["admin"], json={"name": "Fresh", "ou_id": ou.id, "domain_id": domain("AIML").id, "details": {"programme_name": "P"}})
    assert b.status_code == 201
    assert b.get_json()["data"]["code"] in {x["code"] for x in client.get("/api/batches", headers=world["H"]["lead"]).get_json()["data"]}
    lead_id = db.session.query(User).filter_by(email="lead@x.com").one().id
    assert db.session.query(Notification).filter_by(type="batch_assigned", user_id=lead_id).count() == 1
    assert db.session.query(Notification).filter_by(type="batch_in_domain").count() >= 1
    db.session.query(Notification).delete()
    db.session.commit()
    ps = client.post("/api/problem-statements", headers=world["H"]["admin"], json={"title": "Admin project", "domain_id": domain("AIML").id, "description": "d"})
    assert ps.status_code == 201 and ps.get_json()["data"]["approval_status"] == "approved"
    assert ps.get_json()["data"]["ps_code"].startswith("ICT_PS_")
    assert "Admin project" in {x["title"] for x in client.get("/api/problem-statements", headers=world["H"]["lead"]).get_json()["data"]}
    assert db.session.query(Notification).filter_by(type="shelf_project_added").count() >= 2        # lead + domain mentor(s)


def test_only_the_domain_lead_joins_a_batch_by_default_other_mentors_are_added_explicitly(client, world):
    H = world["H"]["lead"]
    for e in ("extra1", "extra2"):
        client.post("/api/admin/users", headers=world["H"]["admin"], json={"role": "mentor", "name": e, "email": f"{e}@x.com", "domain_id": domain("AIML").id})
    client.post("/api/admin/users", headers=world["H"]["admin"], json={"role": "mentor", "name": "iot", "email": "iot2@x.com", "domain_id": domain("IOT").id})
    # new mentors are NOT added automatically (the fixture put only m1 on the batch)
    url = f"/api/batches/{world['batch'].id}/mentors"
    emails = {m["email"] for m in client.get(url, headers=H).get_json()["data"]}
    assert emails == {"m1@x.com"}
    # ...and they are offered when adding mentors; the lead adds the ones wanted explicitly
    ids = {m.user.email: m.id for m in db.session.query(Mentor).all()}
    assert client.post(url + "/bulk", headers=H, json={"mentor_ids": [ids["extra1@x.com"], ids["extra2@x.com"]]}).status_code == 201
    emails = {m["email"] for m in client.get(url, headers=H).get_json()["data"]}
    assert emails == {"m1@x.com", "extra1@x.com", "extra2@x.com"}
    # the one-click "assign whole domain" button remains an explicit action
    r = client.post(f"/api/batches/{world['batch'].id}/mentors/assign-domain", headers=H)
    assert r.status_code == 200 and r.get_json()["message"].startswith("0 mentor")
    assert client.post(f"/api/batches/{world['batch'].id}/mentors/assign-domain", headers=world["H"]["s1"]).status_code == 403
    # a lead can still remove one on purpose, and it is not silently re-added
    mid = db.session.query(Mentor).join(User).filter(User.email == "extra1@x.com").one().id
    assert client.delete(f"/api/batches/{world['batch'].id}/mentors/{mid}", headers=H).status_code == 200
    assert "extra1@x.com" not in {m["email"] for m in client.get(f"/api/batches/{world['batch'].id}/mentors", headers=H).get_json()["data"]}


def test_new_batch_gets_its_domains_mentors_and_admins_are_warned_about_leadless_domains(client, world):
    ou = db.session.query(OrganisationalUnit).first()
    ent = domain("IOT")                                       # IoT has a mentor ("iot@x.com") but NO lead
    db.session.query(Notification).delete()
    db.session.commit()
    b = client.post("/api/batches", headers=world["H"]["admin"], json={"name": "IoT batch", "ou_id": ou.id, "domain_id": ent.id, "details": {"programme_name": "P"}})
    assert b.status_code == 201
    mentors = client.get(f"/api/batches/{b.get_json()['data']['id']}/mentors", headers=world["H"]["admin"]).get_json()["data"]
    assert mentors == []                                      # no lead, and mentors are never added automatically
    warn = db.session.query(Notification).filter_by(type="domain_without_lead").all()
    assert len(warn) == 1 and "no domain lead" in warn[0].message           # goes to the admin
    # creating a shelf project / mentor in that domain warns again
    client.post("/api/problem-statements", headers=world["H"]["admin"], json={"title": "P", "domain_id": ent.id, "description": "d"})
    client.post("/api/admin/users", headers=world["H"]["admin"], json={"role": "mentor", "name": "Zed", "email": "z@x.com", "domain_id": ent.id})
    assert db.session.query(Notification).filter_by(type="domain_without_lead").count() == 3
    # a domain WITH a lead produces no warning
    db.session.query(Notification).delete()
    db.session.commit()
    client.post("/api/problem-statements", headers=world["H"]["admin"], json={"title": "Q", "domain_id": domain("AIML").id, "description": "d"})
    assert db.session.query(Notification).filter_by(type="domain_without_lead").count() == 0


def test_repair_heals_mentorless_batches_but_never_readds_removed_mentors(app, world):
    from app.services import domain_sync_service
    from app.services.domain_sync_service import ensure_lead_mentor_profile
    ensure_lead_mentor_profile(db.session.query(User).filter_by(email="lead@x.com").one(), domain("AIML").id)   # a lead is also a mentor
    db.session.commit()
    admin = db.session.query(User).filter_by(email="admin@x.com").one()
    ou = db.session.query(OrganisationalUnit).first()
    empty = Batch(code="EMPTY", name="E", ou_id=ou.id, domain_id=domain("AIML").id)
    orphan = make_lead = None
    db.session.add(empty)
    db.session.commit()
    report = domain_sync_service.repair(admin)
    db.session.commit()
    assert report["batches_given_mentors"] == [("EMPTY", ["lead@x.com"])]
    assert domain_sync_service.repair(admin)["batches_given_mentors"] == []                    # idempotent
    # report what needs a human
    assert report["domains_without_lead"] == [] and "free@x.com" in report["mentors_without_domain"]
    # B1 still has its mentor removed on purpose? give B1 a different mentor first: not re-added
    db.session.query(BatchMentor).filter_by(batch_id=world["batch"].id).delete()
    other = db.session.query(Mentor).join(User).filter(User.email == "free@x.com").one()
    other.domain_id = domain("AIML").id
    db.session.add(BatchMentor(batch_id=world["batch"].id, mentor_id=other.id))
    db.session.commit()
    domain_sync_service.repair(admin)
    assert {l.mentor_id for l in db.session.query(BatchMentor).filter_by(batch_id=world["batch"].id)} == {other.id}   # m1 not re-added


def test_repair_reports_leads_without_a_domain(app, world, make_user):
    from app.services import domain_sync_service
    make_user("domain_lead", "orphan@x.com")
    db.session.commit()
    assert domain_sync_service.repair(None)["leads_without_domain"] == ["orphan@x.com"]


def test_new_batch_gets_only_the_domain_lead_as_mentor(client, world):
    from app.services.domain_sync_service import ensure_lead_mentor_profile
    ensure_lead_mentor_profile(db.session.query(User).filter_by(email="lead@x.com").one(), domain("AIML").id)   # a lead is also a mentor
    db.session.commit()
    ou = db.session.query(OrganisationalUnit).first()
    b = client.post("/api/batches", headers=world["H"]["admin"], json={"name": "AI batch", "ou_id": ou.id, "domain_id": domain("AIML").id,
                                                                       "details": {"programme_name": "P"}})
    assert b.status_code == 201
    mentors = client.get(f"/api/batches/{b.get_json()['data']['id']}/mentors", headers=world["H"]["admin"]).get_json()["data"]
    assert [m["email"] for m in mentors] == ["lead@x.com"]          # m1 (an AIML mentor) is not added automatically
