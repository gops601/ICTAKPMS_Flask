import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit,
                        ProblemStatement, Project, ProjectStudent, Student)
from app.permissions import scope


@pytest.mark.parametrize("role,expected", [("admin", 200), ("domain_lead", 403), ("mentor", 403), ("student", 403)])
def test_admin_endpoint_role_matrix(client, make_user, login, role, expected):
    make_user(role, f"{role}@x.com")
    r = client.get("/api/admin/users", headers=login(f"{role}@x.com"))
    assert r.status_code == expected


def test_role_comes_from_db_not_token(client, make_user, login):
    u = make_user("admin", "a@x.com")
    h = login("a@x.com")
    from app.models import Role
    u.role_id = db.session.query(Role).filter_by(name="student").one().id  # demoted after token issued
    db.session.commit()
    assert client.get("/api/admin/users", headers=h).status_code == 403


def test_admin_can_create_user_and_duplicate_rejected(client, make_user, login):
    make_user("admin", "a@x.com")
    h = login("a@x.com")
    body = {"role": "mentor", "name": "Mentor One", "email": "m1@x.com", "password": "Passw0rd!x"}
    assert client.post("/api/admin/users", headers=h, json=body).status_code == 201
    assert client.post("/api/admin/users", headers=h, json=body).status_code == 409
    assert client.post("/api/admin/users", headers=h, json={**body, "role": "hacker"}).status_code == 422


@pytest.fixture()
def world(app, make_user):
    """Two domains, one batch each, a lead per domain, a mentor on batch A, a student+project in A."""
    ou = db.session.query(OrganisationalUnit).first()
    dom_a, dom_b = db.session.query(Domain).order_by(Domain.id).limit(2).all()
    batch_a = Batch(code="A1", name="A", ou_id=ou.id, domain_id=dom_a.id)
    batch_b = Batch(code="B1", name="B", ou_id=ou.id, domain_id=dom_b.id)
    db.session.add_all([batch_a, batch_b])
    lead_a, lead_b = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=lead_a.id, domain_id=dom_a.id),
                        DomainLead(user_id=lead_b.id, domain_id=dom_b.id)])
    mu = make_user("mentor", "m@x.com")
    mentor = Mentor(user_id=mu.id, domain_id=dom_a.id)
    db.session.add(mentor)
    su = make_user("student", "s@x.com")
    other_su = make_user("student", "s2@x.com")
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch_a.id, mentor_id=mentor.id))
    s = Student(user_id=su.id, batch_id=batch_a.id, registration_no="R1")
    s2 = Student(user_id=other_su.id, batch_id=batch_a.id, registration_no="R2")
    ps = ProblemStatement(ps_code="PS1", title="T", domain_id=dom_a.id)
    db.session.add_all([s, s2, ps])
    db.session.flush()
    p = Project(batch_id=batch_a.id, problem_statement_id=ps.id)
    db.session.add(p)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=p.id, student_id=s.id))
    db.session.commit()
    return dict(batch_a=batch_a, batch_b=batch_b, project=p, lead_a=lead_a, lead_b=lead_b, mentor=mu,
                student=su, other_student=other_su)


def test_domain_lead_isolated_to_own_domain(world):
    assert scope.can_access_batch(world["lead_a"], world["batch_a"])
    assert not scope.can_access_batch(world["lead_a"], world["batch_b"])
    assert scope.can_access_project(world["lead_a"], world["project"])
    assert not scope.can_access_project(world["lead_b"], world["project"])


def test_mentor_only_assigned_batches(world):
    assert scope.can_access_batch(world["mentor"], world["batch_a"])
    assert not scope.can_access_batch(world["mentor"], world["batch_b"])
    assert scope.can_access_project(world["mentor"], world["project"])


def test_student_only_own_project(world):
    assert scope.can_access_project(world["student"], world["project"])
    assert not scope.can_access_project(world["other_student"], world["project"])


def test_scoped_queries_filter_rows(world):
    ids = lambda u: {b.id for b in db.session.scalars(scope.scoped_batches(u))}  # noqa: E731
    assert ids(world["lead_a"]) == {world["batch_a"].id}
    assert ids(world["lead_b"]) == {world["batch_b"].id}
    assert ids(world["mentor"]) == {world["batch_a"].id}
    assert len(list(db.session.scalars(scope.scoped_projects(world["other_student"])))) == 0
    assert len(list(db.session.scalars(scope.scoped_projects(world["student"])))) == 1


def test_ensure_access_returns_404_not_403(world):
    from app.utils.errors import NotFound
    with pytest.raises(NotFound):
        scope.ensure_batch_access(world["lead_a"], world["batch_b"].id)
    with pytest.raises(NotFound):
        scope.ensure_project_access(world["other_student"], world["project"].id)
