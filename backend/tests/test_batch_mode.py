from datetime import date

from app.extensions import db
from app.models import Batch, ProjectReview
from tests.test_student_shelf import domain, world  # noqa: F401


def create(client, world, **kw):   # noqa: F811
    from app.models import OrganisationalUnit
    ou = db.session.query(OrganisationalUnit).first()
    body = {"name": "M batch", "ou_id": ou.id, "domain_id": domain("AIML").id, "details": {"programme_name": "P"}, **kw}
    return client.post("/api/batches", headers=world["H"]["admin"], json=body)


def test_batch_defaults_to_online_and_asks_for_the_mode(client, world):          # noqa: F811
    d = create(client, world).get_json()["data"]
    assert d["mode"] == "online" and d["total_weeks"] == 4
    d = create(client, world, mode="offline").get_json()["data"]
    assert d["mode"] == "offline" and d["total_weeks"] == 3
    assert create(client, world, mode="hybrid").status_code == 422


def allocate(client, world, batch_id, mentor_id):   # noqa: F811
    from app.models import ProblemStatement, Student
    from tests.test_student_shelf import ProblemStatement  # noqa: F401
    ps = ProblemStatement(ps_code="PX", title="T", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.commit()
    stud = db.session.query(Student).filter_by(batch_id=batch_id).first()
    return client.post("/api/project-allocation", headers=world["H"]["admin"],
                       json={"batch_id": batch_id, "items": [{"problem_statement_id": ps.id, "student_ids": [stud.id]}], "start_date": "2026-03-02"})


def test_offline_projects_run_three_weeks_and_online_four(client, world):        # noqa: F811
    from app.models import Student, User
    off = create(client, world, mode="offline").get_json()["data"]
    db.session.add(Student(user_id=db.session.query(User).filter_by(email="s1@x.com").one().id, batch_id=off["id"], registration_no="O1")) if False else None
    # reuse the world's student: move them into the offline batch
    s = db.session.query(Student).first()
    s.batch_id = off["id"]
    db.session.commit()
    r = allocate(client, world, off["id"], None)
    assert r.status_code in (200, 201), r.get_json()
    p = r.get_json()["data"][0]
    assert p["mode"] == "offline" and p["total_weeks"] == 3 and [w["phase"] for w in p["week_plan"]] == ["SRS & datasets", "Implementation", "Implementation"]
    assert p["target_end_date"] == "2026-03-23"
    weeks = [r.week_no for r in db.session.query(ProjectReview).filter_by(project_id=p["id"]).order_by(ProjectReview.week_no)]
    assert weeks == [1, 2, 3]
    # students see the same 3-week plan on their reviews page, with phases
    rv = client.get(f"/api/reviews/projects/{p['id']}", headers=world["H"]["s1"]).get_json()["data"]
    assert rv["overall"]["reviews_total"] == 3 and [x["phase"] for x in rv["reviews"]] == ["SRS & datasets", "Implementation", "Implementation"]


def test_mode_cannot_change_once_projects_exist(client, world):                  # noqa: F811
    from app.models import Student
    off = create(client, world, mode="offline").get_json()["data"]
    assert client.put(f"/api/batches/{off['id']}", headers=world["H"]["admin"], json={"mode": "online"}).get_json()["data"]["mode"] == "online"
    s = db.session.query(Student).first()
    s.batch_id = off["id"]
    db.session.commit()
    assert allocate(client, world, off["id"], None).status_code in (200, 201)
    r = client.put(f"/api/batches/{off['id']}", headers=world["H"]["admin"], json={"mode": "offline"})
    assert r.status_code == 409 and "cannot switch" in r.get_json()["message"]


def test_students_carry_their_batch_mode(client, world):                         # noqa: F811
    s = client.get("/api/students", headers=world["H"]["admin"]).get_json()["data"][0]
    assert s["batch"]["mode"] == "online"


def test_an_offline_project_needs_only_three_reviews_to_finish(client, world):    # noqa: F811
    from app.models import Project, Student
    from app.services import lifecycle
    off = create(client, world, mode="offline").get_json()["data"]
    db.session.query(Student).first().batch_id = off["id"]
    db.session.commit()
    pid = allocate(client, world, off["id"], None).get_json()["data"][0]["id"]
    project = db.session.get(Project, pid)
    assert "three weekly reviews" in lifecycle._guard(project, "final_evaluation")
    for r in db.session.query(ProjectReview).filter_by(project_id=pid):
        r.status = "submitted"
    db.session.commit()
    assert lifecycle._guard(project, "final_evaluation") is None
