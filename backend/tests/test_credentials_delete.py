import pytest

from app.extensions import db
from app.models import (AuditLog, Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit, ProblemStatement,
                        Project, ProjectStudent, Student, User)
from app.services.auth_service import create_user


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    admin = make_user("admin", "admin@x.com")
    make_user("admin", "admin2@x.com")
    # a lead and a mentor who have never logged in (must_change_password) and one who has
    new_lead = create_user("domain_lead", "Fresh Lead", "freshlead@x.com", "Passw0rd!x", must_change_password=True)
    active_lead = make_user("domain_lead", "activelead@x.com")
    new_m = create_user("mentor", "Fresh Mentor", "freshm@x.com", "Passw0rd!x", must_change_password=True)
    active_m = make_user("mentor", "activem@x.com")
    db.session.flush()
    db.session.add_all([DomainLead(user_id=new_lead.id, domain_id=domain("AIML").id),
                        DomainLead(user_id=active_lead.id, domain_id=domain("IOT").id)])
    fm = Mentor(user_id=new_m.id, designation="Trainer")
    am = Mentor(user_id=active_m.id, mentor_type="industry", company="Acme", industry_sector="Health", designation="CTO", bio="b")
    db.session.add_all([fm, am])
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    db.session.flush()
    su = make_user("student", "free@x.com")
    sp = make_user("student", "placed@x.com")
    db.session.flush()
    free = Student(user_id=su.id, batch_id=batch.id, registration_no="F1")
    placed = Student(user_id=sp.id, batch_id=batch.id, registration_no="P1")
    db.session.add_all([free, placed])
    ps = ProblemStatement(ps_code="PS", title="T", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.flush()
    pr = Project(batch_id=batch.id, problem_statement_id=ps.id, title="P")
    db.session.add(pr)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=pr.id, student_id=placed.id))
    db.session.commit()
    H = {"admin": login("admin@x.com"), "lead": login("activelead@x.com"), "mentor": login("activem@x.com"),
         "student": login("free@x.com")}
    return dict(H=H, admin=admin, batch=batch, users=dict(new_lead=new_lead, active_lead=active_lead, new_m=new_m,
                                                           active_m=active_m, free=su, placed=sp), fm=fm, am=am)


# ------------------------------------------------------------------ credentials
def test_mentor_credentials_issue_new_passwords_and_skip_active_users(client, world):
    r = client.post("/api/admin/users/credentials", headers=world["H"]["admin"], json={"role": "mentor"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert [c["email"] for c in d["credentials"]] == ["freshm@x.com"]
    c = d["credentials"][0]
    assert c["temporary_password"] and c["details"].startswith("Internal mentor") and c["designation"] == "Trainer"
    assert [s["email"] for s in d["skipped"]] == ["activem@x.com"] and "own password" in d["skipped"][0]["reason"]
    # the issued password really works, and must be changed
    login = client.post("/api/auth/login", json={"email": "freshm@x.com", "password": c["temporary_password"]})
    assert login.status_code == 200 and login.get_json()["data"]["user"]["must_change_password"] is True


def test_domain_lead_credentials_include_their_domains(client, world):
    d = client.post("/api/admin/users/credentials", headers=world["H"]["admin"], json={"role": "domain_lead"}).get_json()["data"]
    assert [c["email"] for c in d["credentials"]] == ["freshlead@x.com"] and d["credentials"][0]["details"] == "AI & ML"


def test_credentials_can_be_limited_to_selected_users_and_are_admin_only(client, world):
    ids = [world["users"]["new_m"].id]
    d = client.post("/api/admin/users/credentials", headers=world["H"]["admin"], json={"role": "mentor", "user_ids": ids}).get_json()["data"]
    assert len(d["credentials"]) == 1 and d["skipped"] == []
    for who in ("lead", "mentor", "student"):
        assert client.post("/api/admin/users/credentials", headers=world["H"][who], json={"role": "mentor"}).status_code == 403
    assert client.post("/api/admin/users/credentials", headers=world["H"]["admin"], json={"role": "student"}).status_code == 422
    assert db.session.query(AuditLog).filter_by(action="staff.credentials_issued").count() == 1


# ------------------------------------------------------------------------ delete
def delete(client, world, user, who="admin"):
    return client.delete(f"/api/admin/users/{user.id}", headers=world["H"][who])


def test_delete_requires_admin(client, world):
    for who in ("lead", "mentor", "student"):
        assert delete(client, world, world["users"]["free"], who).status_code == 403
    assert delete(client, world, world["users"]["free"]).status_code == 200


def test_delete_student_without_project_removes_account_and_profile(client, world):
    u = world["users"]["free"]
    uid = u.id
    r = delete(client, world, u)
    assert r.status_code == 200
    assert db.session.get(User, uid) is None and db.session.query(Student).filter_by(registration_no="F1").count() == 0
    assert db.session.query(AuditLog).filter_by(action="user.delete", entity_id=uid).count() == 1
    assert client.get("/api/admin/users", headers=world["H"]["admin"]).status_code == 200


def test_student_with_a_project_cannot_be_deleted(client, world):
    r = delete(client, world, world["users"]["placed"])
    assert r.status_code == 409 and "Deactivate" in r.get_json()["message"]
    assert db.session.get(User, world["users"]["placed"].id) is not None


def test_mentor_with_batch_cannot_be_deleted_until_removed(client, world):
    db.session.add(BatchMentor(batch_id=world["batch"].id, mentor_id=world["fm"].id))
    db.session.commit()
    r = delete(client, world, world["users"]["new_m"])
    assert r.status_code == 409 and "Reassign" in r.get_json()["message"]
    db.session.query(BatchMentor).delete()
    db.session.commit()
    assert delete(client, world, world["users"]["new_m"]).status_code == 200
    assert db.session.query(Mentor).filter_by(id=world["fm"].id).count() == 0


def test_sole_lead_of_a_domain_with_batches_cannot_be_deleted(client, world):
    r = delete(client, world, world["users"]["new_lead"])     # only lead of AIML, which has batch B1
    assert r.status_code == 409 and "only lead" in r.get_json()["message"]
    assert delete(client, world, world["users"]["active_lead"]).status_code == 200   # IOT has no batches


def test_admins_cannot_delete_themselves_or_the_last_admin(client, world):
    assert delete(client, world, world["admin"]).status_code == 409                 # self
    other = db.session.query(User).filter_by(email="admin2@x.com").one()
    assert delete(client, world, other).status_code == 200                          # allowed: another admin remains
    db.session.query(User).filter_by(email="admin2@x.com").count()
    assert client.delete("/api/admin/users/99999", headers=world["H"]["admin"]).status_code == 404


# ------------------------------------------------------------------ delete batch
def make_batch(code="DB1"):
    ou = db.session.query(OrganisationalUnit).first()
    b = Batch(code=code, name="Disposable", ou_id=ou.id, domain_id=domain("IOT").id)
    db.session.add(b)
    db.session.commit()
    return b


def test_delete_empty_batch_is_admin_only_and_audited(client, world):
    b = make_batch()
    for who in ("lead", "mentor", "student"):
        assert client.delete(f"/api/batches/{b.id}", headers=world["H"][who]).status_code == 403
    bid = b.id
    assert client.delete(f"/api/batches/{bid}", headers=world["H"]["admin"]).status_code == 200
    assert db.session.get(Batch, bid) is None
    assert db.session.query(AuditLog).filter_by(action="batch.delete", entity_id=bid).count() == 1
    assert client.delete(f"/api/batches/{bid}", headers=world["H"]["admin"]).status_code == 404


def test_batch_with_projects_cannot_be_deleted(client, world):
    r = client.delete(f"/api/batches/{world['batch'].id}", headers=world["H"]["admin"])     # B1 has a project
    assert r.status_code == 409 and "Close the batch" in r.get_json()["message"]
    assert db.session.get(Batch, world["batch"].id) is not None


def test_batch_with_students_needs_the_explicit_option_and_removes_their_accounts(client, world, make_user):
    b = make_batch("DB2")
    u = make_user("student", "gone@x.com")
    db.session.flush()
    db.session.add(Student(user_id=u.id, batch_id=b.id, registration_no="G1"))
    db.session.commit()
    uid, bid = u.id, b.id
    r = client.delete(f"/api/batches/{bid}", headers=world["H"]["admin"])
    assert r.status_code == 409 and r.get_json()["errors"]["student_count"] == 1
    assert db.session.get(Batch, bid) is not None
    r = client.delete(f"/api/batches/{bid}?with_students=1", headers=world["H"]["admin"])
    assert r.status_code == 200
    db.session.expire_all()
    assert db.session.get(Batch, bid) is None and db.session.get(User, uid) is None
