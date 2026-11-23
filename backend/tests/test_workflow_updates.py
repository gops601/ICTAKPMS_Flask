import re

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit, ProblemStatement, Project,
                        Student)

ICT = re.compile(r"^ICT_[A-Z]+_[A-Z2-9]{6}$")


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id),
                        DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    m1u, m2u = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com")
    m1, m2 = Mentor(user_id=m1u.id), Mentor(user_id=m2u.id)
    db.session.add_all([m1, m2])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    studs = {}
    for n in ("s1", "s2", "s3"):
        u = make_user("student", f"{n}@x.com")
        db.session.flush()
        studs[n] = Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper())
        db.session.add(studs[n])
    ps = ProblemStatement(ps_code="PS1", title="P", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "la", "lb", "m1", "m2", "s1", "s2", "s3")}
    return dict(H=H, batch=batch, studs=studs, ps=ps)


def allocate(client, world, who, students, team=False):
    return client.post("/api/project-allocation", headers=world["H"][who], json={
        "batch_id": world["batch"].id, "mentor_id": None, "start_date": None,
        "items": [{"problem_statement_id": world["ps"].id, "student_ids": [world["studs"][s].id for s in students],
                   "team": team}]})


# ------------------------------------------------- mentors allocate (student or group)
def test_mentor_allocates_to_a_student_and_a_group_with_ict_project_ids(client, world):
    r = allocate(client, world, "m1", ["s1"])
    assert r.status_code == 201, r.get_json()
    r2 = allocate(client, world, "m1", ["s2", "s3"], team=True)
    assert r2.status_code == 201
    codes = [p.code for p in db.session.query(Project).all()]
    assert len(codes) == 2 and all(ICT.match(c) for c in codes) and len(set(codes)) == 2
    assert r2.get_json()["data"][0]["code"] == codes[1] and len(r2.get_json()["data"][0]["members"]) == 2


def test_mentor_not_on_batch_cannot_allocate_and_lead_still_can(client, world):
    assert allocate(client, world, "m2", ["s1"]).status_code == 404
    assert allocate(client, world, "lb", ["s1"]).status_code == 404
    assert allocate(client, world, "la", ["s1"]).status_code == 201


# -------------------------------------------------------------------------- feedback
def feedback(client, world, who, pid, message="Good progress", student_id=None):
    return client.post(f"/api/projects/{pid}/feedback", headers=world["H"][who],
                       json={"message": message, "student_id": student_id})


def test_mentor_feedback_to_team_and_to_one_student(client, world):
    allocate(client, world, "m1", ["s2", "s3"], team=True)
    pid = db.session.query(Project).one().id
    assert feedback(client, world, "m1", pid, "Team: tidy the repo").status_code == 201
    assert feedback(client, world, "m1", pid, "Only for s2", world["studs"]["s2"].id).status_code == 201
    see = lambda who: {f["message"] for f in client.get(f"/api/projects/{pid}/feedback", headers=world["H"][who]).get_json()["data"]}  # noqa: E731
    assert see("s2") == {"Team: tidy the repo", "Only for s2"}
    assert see("s3") == {"Team: tidy the repo"}          # private feedback is not shown to teammates
    assert len(see("m1")) == 2 and len(see("la")) == 2


def test_feedback_rules(client, world):
    allocate(client, world, "m1", ["s1"])
    pid = db.session.query(Project).one().id
    assert feedback(client, world, "s1", pid).status_code == 403          # students cannot send
    assert feedback(client, world, "la", pid).status_code == 403
    assert feedback(client, world, "m2", pid).status_code == 404          # not their project
    assert feedback(client, world, "m1", pid, "  ").status_code in (422,)
    assert feedback(client, world, "m1", pid, student_id=world["studs"]["s2"].id).status_code == 422  # not a member
    from app.models import Notification
    feedback(client, world, "m1", pid, "Nice")
    assert db.session.query(Notification).filter_by(type="mentor_feedback").count() == 1
    assert client.get(f"/api/projects/{pid}/feedback", headers=world["H"]["s2"]).status_code == 404


# ---------------------------------------------------------- close / reopen by the lead
def complete(pid):
    from app.models.base import utcnow
    p = db.session.get(Project, pid)
    p.stage, p.completed_at = "completed", utcnow()
    db.session.commit()


def test_lead_closes_completed_project_and_can_reopen_it(client, world):
    allocate(client, world, "la", ["s1"])
    pid = db.session.query(Project).one().id
    assert client.post(f"/api/projects/{pid}/close", headers=world["H"]["la"]).status_code == 409   # not completed yet
    complete(pid)
    for who in ("m1", "s1"):
        assert client.post(f"/api/projects/{pid}/close", headers=world["H"][who]).status_code == 403
    assert client.post(f"/api/projects/{pid}/close", headers=world["H"]["lb"]).status_code == 404
    r = client.post(f"/api/projects/{pid}/close", headers=world["H"]["la"])
    assert r.status_code == 200 and r.get_json()["data"]["is_closed"] is True
    assert client.post(f"/api/projects/{pid}/close", headers=world["H"]["la"]).status_code == 409   # already closed
    rr = client.post(f"/api/projects/{pid}/reopen", headers=world["H"]["la"],
                     json={"to": "implementation", "reason": "Needs more work"})
    assert rr.status_code == 200
    d = rr.get_json()["data"]
    assert d["stage"] == "implementation" and d["is_closed"] is False and d["closed_at"] is None


# ------------------------------------------------------------------ generated ids
def test_student_registration_number_is_generated_when_blank(client, world):
    r = client.post("/api/students", headers=world["H"]["admin"],
                    json={"name": "New Student", "email": "new@x.com", "batch_id": world["batch"].id})
    assert r.status_code == 201, r.get_json()
    assert ICT.match(r.get_json()["data"]["student"]["registration_no"]) if "student" in r.get_json()["data"] \
        else ICT.match(r.get_json()["data"]["registration_no"])


def test_id_generator_mixes_letters_and_digits():
    from app.utils.ids import generate_id
    ids = {generate_id("PRJ", lambda c: False) for _ in range(200)}
    assert all(ICT.match(i) and re.search(r"\d", i[8:]) and re.search(r"[A-Z]", i[8:]) for i in ids)
