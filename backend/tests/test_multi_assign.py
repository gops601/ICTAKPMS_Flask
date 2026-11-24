from app.extensions import db
from app.models import Mentor, Notification, ProjectMentor, ScrumTaskAssignee, User
from tests.test_scrum import add, world  # noqa: F401


def put_mentors(client, who, project, ids, reason=None):
    return client.put(f"/api/projects/{project.id}/mentors", headers=who, json={"mentor_ids": ids, "reason": reason})


def test_admin_assigns_several_mentors_to_a_project(client, world):            # noqa: F811
    m1 = db.session.query(Mentor).join(User).filter(User.email == "m1@x.com").one()
    p = world["team"]
    assert client.get(f"/api/projects/{p.id}", headers=world["H"]["m2"]).status_code == 404          # not theirs yet
    db.session.query(Notification).delete()
    db.session.commit()
    r = put_mentors(client, world["H"]["admin"], p, [m1.id, world["m2"].id], "extra guidance")
    assert r.status_code == 200
    assert {m["name"] for m in r.get_json()["data"]["mentors"]} == {m1.user.name, world["m2"].user.name} and len(r.get_json()["data"]["mentors"]) == 2
    assert client.get(f"/api/projects/{p.id}", headers=world["H"]["m2"]).status_code == 200            # the added mentor now sees it
    assert client.get(f"/api/projects", headers=world["H"]["m2"]).get_json()["data"][0]["id"] == p.id
    assert db.session.query(ProjectMentor).filter_by(project_id=p.id).count() == 2
    assert db.session.query(Notification).filter_by(user_id=world["m2"].user_id, type="project_allocated").count() == 1
    assert db.session.query(Notification).filter_by(user_id=world["s1u"].id, type="mentor_assigned").count() == 1
    # back to one mentor, then to the batch default
    assert len(put_mentors(client, world["H"]["admin"], p, [m1.id]).get_json()["data"]["mentors"]) == 1
    assert client.get(f"/api/projects/{p.id}", headers=world["H"]["m2"]).status_code == 404
    r = put_mentors(client, world["H"]["admin"], p, [])
    assert r.status_code == 200 and r.get_json()["data"]["mentor_override"] is False and db.session.query(ProjectMentor).filter_by(project_id=p.id).count() == 0


def test_domain_lead_picks_only_batch_mentors_and_students_cannot(client, world):   # noqa: F811
    p = world["team"]
    assert put_mentors(client, world["H"]["la"], p, [world["m2"].id]).status_code == 422             # m2 is not on the batch
    assert put_mentors(client, world["H"]["lb"], p, []).status_code == 404                          # another domain's lead
    for who in ("m1", "s1"):
        assert put_mentors(client, world["H"][who], p, []).status_code == 403


def test_a_task_can_be_assigned_to_several_students(client, world):            # noqa: F811
    sid = [world["studs"]["s1"].id, world["studs"]["s2"].id]
    db.session.query(Notification).delete()
    db.session.commit()
    t = add(client, world, "m1", world["team"], assigned_student_ids=sid).get_json()["data"]
    assert [a["student_id"] for a in t["assignees"]] == sid and t["assignee"]["student_id"] == sid[0]
    assert db.session.query(Notification).filter_by(user_id=world["s2u"].id, type="task_assigned").count() == 1
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"assigned_student_ids": [sid[1]], "version": t["version"]})
    assert r.status_code == 200 and [a["student_id"] for a in r.get_json()["data"]["assignees"]] == [sid[1]]
    d = client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"]).get_json()["data"]
    assert any(h["action"] == "assigned" for h in d["history"])
    # clearing, and the older single-id form still works
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"assigned_student_ids": []})
    assert r.get_json()["data"]["assignees"] == [] and r.get_json()["data"]["assignee"] is None
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"assigned_student_id": sid[0]})
    assert [a["student_id"] for a in r.get_json()["data"]["assignees"]] == [sid[0]]
    assert db.session.query(ScrumTaskAssignee).filter_by(task_id=t["id"]).count() == 1


def test_every_assignee_must_be_a_project_member(client, world):                # noqa: F811
    outsider = world["studs"]["s3"].id
    r = add(client, world, "s1", world["team"], assigned_student_ids=[world["studs"]["s1"].id, outsider])
    assert r.status_code == 422 and "assigned_student_ids" in r.get_json()["errors"]
