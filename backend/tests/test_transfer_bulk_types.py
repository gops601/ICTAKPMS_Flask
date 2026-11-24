import io

from app.extensions import db
from app.models import Batch, BatchMentor, Mentor, OrganisationalUnit, Project, ProjectMentor, ScrumTask, User
from tests.test_scrum import board, domain, world  # noqa: F401  (fixture)


def csv_file(text, name="tasks.csv"):
    return {"file": (io.BytesIO(text.encode()), name)}


def upload(client, world, who, project, text, name="tasks.csv"):          # noqa: F811
    return client.post(f"/api/scrum/projects/{project.id}/tasks/bulk", headers=world["H"][who], data=csv_file(text, name),
                       content_type="multipart/form-data")


# ------------------------------------------------------------ mentor remove / replace
def test_admin_replaces_a_mentor_everywhere(client, world):                    # noqa: F811
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    p = world["team"]
    db.session.add(ProjectMentor(project_id=p.id, mentor_id=m1.id))
    p.mentor_id = m1.id
    db.session.commit()
    r = client.post(f"/api/mentors/{m1.id}/transfer", headers=world["H"]["admin"], json={"to_mentor_id": world["m2"].id})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["batches"] == 1 and r.get_json()["data"]["projects"] >= 1
    db.session.expire_all()
    assert not db.session.query(BatchMentor).filter_by(mentor_id=m1.id, is_active=True).count()
    assert db.session.query(BatchMentor).filter_by(mentor_id=world["m2"].id, is_active=True).count() == 1
    assert [m["name"] for m in client.get(f"/api/projects/{p.id}", headers=world["H"]["m2"]).get_json()["data"]["mentors"]] == [world["m2"].user.name]
    assert client.get(f"/api/projects/{p.id}", headers=world["H"]["m1"]).status_code == 404


def test_domain_lead_can_remove_without_replacement_but_only_in_own_domain(client, world):    # noqa: F811
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    assert client.post(f"/api/mentors/{m1.id}/transfer", headers=world["H"]["lb"], json={"to_mentor_id": None}).get_json()["data"]["batches"] == 0
    assert db.session.query(BatchMentor).filter_by(mentor_id=m1.id, is_active=True).count() == 1       # other domain's lead: untouched
    r = client.post(f"/api/mentors/{m1.id}/transfer", headers=world["H"]["la"], json={"to_mentor_id": None})
    assert r.status_code == 200 and r.get_json()["data"]["batches"] == 1
    assert db.session.query(BatchMentor).filter_by(mentor_id=m1.id, is_active=True).count() == 0


def test_transfer_validation_and_roles(client, world):                          # noqa: F811
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    url = f"/api/mentors/{m1.id}/transfer"
    assert client.post(url, headers=world["H"]["admin"], json={"to_mentor_id": m1.id}).status_code == 422
    assert client.post(url, headers=world["H"]["m1"], json={"to_mentor_id": None}).status_code == 403
    assert client.post(url, headers=world["H"]["s1"], json={"to_mentor_id": None}).status_code == 403
    assert client.post(url, headers=world["H"]["admin"], json={"to_mentor_id": 9999}).status_code == 404
    assert client.post(url, headers=world["H"]["admin"], json={}).status_code == 422


# ------------------------------------------------------------ students never see mentor contact details
def test_students_see_only_mentor_names(client, world):              # noqa: F811
    world["m1u"].phone = "+91 90000 11111"
    db.session.commit()
    for who in ("s1", "s2"):
        detail = client.get(f"/api/projects/{world['team'].id}", headers=world["H"][who]).get_json()["data"]
        assert detail["mentors"] and all(set(m) == {"id", "name"} for m in detail["mentors"])
        listed = client.get("/api/projects", headers=world["H"][who]).get_json()["data"]
        assert all("email" not in m and "phone" not in m for p in listed for m in p["mentors"])
    rows = client.get("/api/my/mentors", headers=world["H"]["s1"]).get_json()["data"]       # the group's mentors, names only
    assert [set(r) for r in rows] == [{"id", "name"}] and rows[0]["name"] == world["m1u"].name
    assert client.get("/api/my/mentors", headers=world["H"]["m1"]).status_code == 403
    # a student without a project sees no mentors, even though the batch has one
    from app.models import Project, ProjectStudent
    db.session.query(ProjectStudent).filter_by(student_id=world["studs"]["s1"].id).delete()
    db.session.commit()
    assert client.get("/api/my/mentors", headers=world["H"]["s1"]).get_json()["data"] == []
    # staff still get the details
    for who in ("m1", "la", "admin"):
        m = client.get(f"/api/projects/{world['team'].id}", headers=world["H"][who]).get_json()["data"]["mentors"][0]
        assert m["email"] == "m1@x.com" and m["phone"] == "+91 90000 11111"


# ------------------------------------------------------------ weekly bulk upload
def test_template_downloads(client, world):                                     # noqa: F811
    url = f"/api/scrum/projects/{world['team'].id}/tasks/template"
    r = client.get(url + "?format=xlsx", headers=world["H"]["s1"])
    assert r.status_code == 200 and r.data[:2] == b"PK"
    r = client.get(url + "?format=csv", headers=world["H"]["m1"])
    assert r.status_code == 200 and r.data.decode("utf-8-sig").splitlines()[0].startswith("Task Title,Description,Week")
    assert client.get(url, headers=world["H"]["s3"]).status_code == 404


def test_bulk_upload_creates_tasks_with_assignees_and_week_dates(client, world):    # noqa: F811
    p = world["team"]
    from datetime import date
    p.start_date = date(2026, 1, 5)
    db.session.commit()
    text = ("Task Title,Description,Week,Priority,Status,Assigned To,Start Date,Due Date\n"
            "Build API,endpoints,2,high,In Progress,s1@x.com;S2,,\n"
            "Write docs,,,low,,,2026-01-06,2026-01-09\n")
    r = upload(client, world, "s1", p, text)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["created"] == 2
    tasks = {t.title: t for t in db.session.query(ScrumTask).all()}
    api = tasks["Build API"]
    assert api.status == "in_progress" and api.priority == "high" and str(api.start_date) == "2026-01-12" and str(api.due_date) == "2026-01-18"
    assert len([a for a in r.get_json()["data"]["board"]["columns"] if a["status"] == "todo"][0]["tasks"]) == 1   # default status = todo
    assert len(client.get(f"/api/scrum/tasks/{api.id}", headers=world["H"]["s1"]).get_json()["data"]["assignees"]) == 2


def test_bulk_upload_is_all_or_nothing_and_reports_rows(client, world):         # noqa: F811
    text = ("Task Title,Priority,Assigned To,Week\n"
            "Good one,high,s1@x.com,1\n"
            ",low,,\n"
            "Bad assignee,low,s3@x.com,\n"
            "Bad priority,urgent,,9\n")
    r = upload(client, world, "m1", world["team"], text)
    data = r.get_json()["data"]
    assert r.status_code == 200 and data["created"] == 0
    assert [e["row"] for e in data["errors"]] == [3, 4, 5]
    assert "not a member" in data["errors"][1]["message"] and "Priority" in data["errors"][2]["message"] and "Week" in data["errors"][2]["message"]
    assert db.session.query(ScrumTask).count() == 0


def test_bulk_upload_permissions_and_bad_files(client, world):                  # noqa: F811
    good = "Task Title\nOne\n"
    assert upload(client, world, "s3", world["team"], good).status_code == 404                  # not on the project
    assert upload(client, world, "s3", world["locked"], good).status_code == 403                # board still locked
    assert upload(client, world, "la", world["team"], good).status_code == 403                  # leads are read-only
    assert upload(client, world, "s1", world["team"], good, name="tasks.txt").status_code == 422
    assert upload(client, world, "s1", world["team"], "Title only\nx\n").status_code == 422      # no Task Title column
    r = client.post(f"/api/scrum/projects/{world['team'].id}/tasks/bulk", headers=world["H"]["s1"])
    assert r.status_code == 422


# ------------------------------------------------------------ Academic OU project types
def academic_batch(world, make_user):                                             # noqa: F811
    from app.models import ProblemStatement, Student
    ou = db.session.query(OrganisationalUnit).filter_by(code="ACADEMIC").one()
    b = Batch(code="AC1", name="Academic", ou_id=ou.id, domain_id=db.session.query(Batch).one().domain_id)
    db.session.add(b)
    db.session.flush()
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    db.session.add(BatchMentor(batch_id=b.id, mentor_id=m1.id))
    s = Student(user_id=make_user("student", "ac@x.com").id, batch_id=b.id, registration_no="AC1")
    db.session.add(s)
    db.session.commit()
    return b, s, db.session.query(ProblemStatement).first()


def test_academic_projects_need_a_type(client, world, make_user):                            # noqa: F811
    b, s, ps = academic_batch(world, make_user)
    body = {"batch_id": b.id, "items": [{"problem_statement_id": ps.id, "student_ids": [s.id]}]}
    r = client.post("/api/project-allocation", headers=world["H"]["admin"], json=body)
    assert r.status_code == 422 and "project_type" in r.get_json()["errors"]
    assert client.post("/api/project-allocation", headers=world["H"]["admin"], json={**body, "project_type": "bogus"}).status_code == 422
    r = client.post("/api/project-allocation", headers=world["H"]["admin"], json={**body, "project_type": "summer_internship"})
    assert r.status_code == 201, r.get_json()
    d = r.get_json()["data"][0]
    assert d["project_type"] == "summer_internship" and d["project_type_label"] == "Summer Internship"
    listed = client.get("/api/projects?project_type=summer_internship", headers=world["H"]["admin"]).get_json()["data"]
    assert [x["id"] for x in listed] == [d["id"]]
    assert client.get("/api/projects?project_type=addon_course", headers=world["H"]["admin"]).get_json()["data"] == []
    assert client.get(f"/api/batches/{b.id}", headers=world["H"]["admin"]).get_json()["data"]["ou"]["code"] == "ACADEMIC"


def test_other_ous_have_no_project_type(client, world):                          # noqa: F811
    p = world["team"]
    d = client.get(f"/api/projects/{p.id}", headers=world["H"]["admin"]).get_json()["data"]
    assert d["project_type"] is None and d["project_type_label"] is None


# ------------------------------------------------------------ add several mentors to a batch
def test_add_several_mentors_to_a_batch(client, world, make_user):                # noqa: F811
    batch = db.session.query(Batch).one()
    extra = Mentor(user_id=make_user("mentor", "m3@x.com").id)
    db.session.add(extra)
    db.session.commit()
    url = f"/api/batches/{batch.id}/mentors/bulk"
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    r = client.post(url, headers=world["H"]["la"], json={"mentor_ids": [m1.id, world["m2"].id, extra.id]})   # m1 is already on the batch
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["message"] == "2 mentor(s) added" and len(r.get_json()["data"]) == 3
    assert client.post(url, headers=world["H"]["lb"], json={"mentor_ids": [m1.id]}).status_code == 404     # another domain's lead
    assert client.post(url, headers=world["H"]["m1"], json={"mentor_ids": [m1.id]}).status_code == 403
    assert client.post(url, headers=world["H"]["admin"], json={"mentor_ids": []}).status_code == 422
    assert client.post(url, headers=world["H"]["admin"], json={"mentor_ids": [9999]}).status_code == 404
    # the new mentor now sees the batch (and so the proposals its students submit)
    assert client.get(f"/api/batches/{batch.id}", headers=world["H"]["m2"]).status_code == 200
