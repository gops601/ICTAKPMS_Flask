from app.extensions import db
from app.models import Batch, BatchMentor, Mentor, OrganisationalUnit, ScrumBoard, User
from app.services import domain_sync_service
from tests.test_reviews import full, put, rid, submit, world  # noqa: F401
from tests.test_student_shelf import domain


def create_lead(client, world, email="nl@x.com", domains=("AIML",)):                # noqa: F811
    return client.post("/api/admin/users", headers=world["H"]["admin"], json={
        "role": "domain_lead", "name": "New Lead", "email": email, "domain_ids": [domain(c).id for c in domains]})


def mentor_of(email):
    return db.session.query(Mentor).join(User, User.id == Mentor.user_id).filter(User.email == email).first()


def test_a_new_domain_lead_is_automatically_a_mentor_on_the_domains_batches(client, world):   # noqa: F811
    r = create_lead(client, world)
    assert r.status_code == 201, r.get_json()
    m = mentor_of("nl@x.com")
    assert m is not None and m.domain_id == domain("AIML").id and m.designation == "Domain Lead"
    # in the admin's mentor list, flagged as a domain lead
    rows = client.get("/api/mentors", headers=world["H"]["admin"]).get_json()["data"]
    me = next(x for x in rows if x["email"] == "nl@x.com")
    assert me["is_domain_lead"] is True
    # joined the active AIML batch(es) without any manual step
    b1 = db.session.query(Batch).filter_by(code="B1").one()
    assert m.id in {l.mentor_id for l in db.session.query(BatchMentor).filter_by(batch_id=b1.id, is_active=True)}
    emails = {x["email"] for x in client.get(f"/api/batches/{b1.id}/mentors", headers=world["H"]["admin"]).get_json()["data"]}
    assert "nl@x.com" in emails
    # /auth/me tells the UI the lead is also a mentor
    from app.schemas.auth import user_to_dict
    assert user_to_dict(db.session.query(User).filter_by(email="nl@x.com").one())["is_mentor"] is True


def test_a_lead_of_several_domains_is_a_mentor_in_each(client, world):               # noqa: F811
    ou = db.session.query(OrganisationalUnit).first()
    iot = Batch(code="IOTB", name="I", ou_id=ou.id, domain_id=domain("IOT").id)
    db.session.add(iot)
    db.session.commit()
    create_lead(client, world, "multi@x.com", ("AIML", "IOT"))
    m = mentor_of("multi@x.com")
    assert {l.batch_id for l in db.session.query(BatchMentor).filter_by(mentor_id=m.id)} == {
        db.session.query(Batch).filter_by(code="B1").one().id, iot.id}
    # eligible for the batch pickers of both domains
    for d in ("AIML", "IOT"):
        got = client.get(f"/api/mentors?for_domain={domain(d).id}", headers=world["H"]["admin"]).get_json()["data"]
        assert "multi@x.com" in {x["email"] for x in got}


def test_changing_a_leads_domains_keeps_them_a_mentor_and_repair_backfills_old_leads(client, world, app):   # noqa: F811
    assert mentor_of("la@x.com") is None                       # world's lead predates the rule
    admin = db.session.query(User).filter_by(email="admin@x.com").one()
    report = domain_sync_service.repair(admin)
    db.session.commit()
    assert "la@x.com" in report["leads_made_mentors"] and mentor_of("la@x.com") is not None
    b1 = db.session.query(Batch).filter_by(code="B1").one()
    assert mentor_of("la@x.com").id in {l.mentor_id for l in db.session.query(BatchMentor).filter_by(batch_id=b1.id, is_active=True)}
    assert "leads_made_mentors" not in domain_sync_service.repair(admin) or domain_sync_service.repair(admin)["leads_made_mentors"] == []
    la = db.session.query(User).filter_by(email="la@x.com").one()
    r = client.put(f"/api/admin/users/{la.id}/domains", headers=world["H"]["admin"], json={"domain_ids": [domain("IOT").id]})
    assert r.status_code == 200 and mentor_of("la@x.com").domain_id == domain("IOT").id


def test_a_lead_who_mentors_a_project_can_do_the_mentor_work_on_it_only(client, world):   # noqa: F811
    project = world["main"]
    rv = rid(project, 1)
    assert put(client, world, "la", rv, remarks="x").status_code == 403 or put(client, world, "la", rv, remarks="x").status_code == 404   # plain lead: no
    admin = db.session.query(User).filter_by(email="admin@x.com").one()
    domain_sync_service.repair(admin)                            # la becomes a mentor and joins the AIML batch
    db.session.commit()
    # as one of the batch's mentors the lead can now score and give feedback on the batch's projects
    assert put(client, world, "la", rv, remarks="Looks fine", review_date=None).status_code == 200
    assert client.post(f"/api/projects/{project.id}/feedback", headers=world["H"]["la"], json={"message": "Keep going", "student_id": None}).status_code == 201
    perms = client.get(f"/api/reviews/{rv}", headers=world["H"]["la"]).get_json()["data"]["permissions"]
    assert perms["can_edit"] is True
    # a lead of another domain, who is not a mentor, still cannot
    assert put(client, world, "lb", rv, remarks="no").status_code in (403, 404)
    # the lead mentor is told like any other mentor
    from app.services.project_service import mentor_user_ids
    assert db.session.query(User).filter_by(email="la@x.com").one().id in mentor_user_ids(project)


def test_deleting_a_lead_mentor_needs_them_off_their_batches_first(client, world):    # noqa: F811
    create_lead(client, world)
    uid = db.session.query(User).filter_by(email="nl@x.com").one().id
    r = client.delete(f"/api/admin/users/{uid}", headers=world["H"]["admin"])
    assert r.status_code == 409 and "also a mentor" in r.get_json()["message"]
