from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, Notification, OrganisationalUnit, ProblemStatement,
                        Project, ProjectStudent, ScrumBoard, ScrumTask, ScrumTaskHistory, Student)
from app.services.project_service import compute_progress


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id), DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    m1u, m2u = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com")
    m1, m2 = Mentor(user_id=m1u.id), Mentor(user_id=m2u.id)
    db.session.add_all([m1, m2])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    su = {n: make_user("student", f"{n}@x.com") for n in ("s1", "s2", "s3", "s4")}
    db.session.flush()
    studs = {n: Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper()) for n, u in su.items()}
    db.session.add_all(studs.values())
    ps = ProblemStatement(ps_code="PS1", title="T", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.flush()
    projects = {}
    for n, members, stage in (("team", ["s1", "s2"], "implementation"), ("locked", ["s3"], "srs_preparation"), ("other", ["s4"], "implementation")):
        p = Project(batch_id=batch.id, problem_statement_id=ps.id, title=f"Project {n}", stage=stage)
        db.session.add(p)
        db.session.flush()
        for m in members:
            db.session.add(ProjectStudent(project_id=p.id, student_id=studs[m].id))
        db.session.add(ScrumBoard(project_id=p.id))
        projects[n] = p
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "la", "lb", "m1", "m2", "s1", "s2", "s3", "s4")}
    return dict(H=H, team=projects["team"], locked=projects["locked"], other=projects["other"], studs=studs, m1u=m1u,
                s1u=su["s1"], s2u=su["s2"], m2=m2)


def add(client, world, who, project, title="Task", **kw):
    return client.post(f"/api/scrum/projects/{project.id}/tasks", headers=world["H"][who], json={"title": title, **kw})


def board(client, world, who, project):
    r = client.get(f"/api/scrum/projects/{project.id}/board", headers=world["H"][who])
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def col(data, status):
    return next(c for c in data["columns"] if c["status"] == status)["tasks"]


def titles(data, status):
    return [t["title"] for t in col(data, status)]


def move(client, world, who, task_id, status, position=None):
    return client.patch(f"/api/scrum/tasks/{task_id}/move", headers=world["H"][who], json={"status": status, "position": position})


# ---------------------------------------------------------------------- board
def test_board_has_five_columns_in_order(client, world):
    d = board(client, world, "s1", world["team"])
    assert [(c["status"], c["label"]) for c in d["columns"]] == [
        ("backlog", "Backlog"), ("todo", "To Do"), ("in_progress", "In Progress"), ("in_review", "In Review"), ("completed", "Completed")]
    assert d["stats"] == {"total": 0, "completed": 0, "overdue": 0, "completion_pct": 0.0,
                          "by_status": {"backlog": 0, "todo": 0, "in_progress": 0, "in_review": 0, "completed": 0}}
    assert {m["name"] for m in d["members"]} == {"Student", "Student"} or len(d["members"]) == 2


@pytest.mark.parametrize("who,expected", [("s1", 200), ("s2", 200), ("m1", 200), ("la", 200), ("admin", 200),
                                          ("s3", 404), ("s4", 404), ("m2", 404), ("lb", 404)])
def test_board_visibility(client, world, who, expected):
    assert client.get(f"/api/scrum/projects/{world['team'].id}/board", headers=world["H"][who]).status_code == expected


def test_permission_flags_per_role(client, world):
    flags = lambda who: board(client, world, who, world["team"])["permissions"]  # noqa: E731
    s = flags("s1")
    assert s["can_create"] and s["can_edit"] and s["can_move"] and s["can_delete"] and s["can_comment"] and s["reason"] is None
    m = flags("m1")
    assert not m["can_create"] and not m["can_edit"] and not m["can_move"] and m["can_comment"] and "comment" in m["reason"]
    la = flags("la")
    assert not any(la[k] for k in ("can_create", "can_edit", "can_move", "can_comment")) and "read-only" in la["reason"]
    assert flags("admin")["can_comment"] and not flags("admin")["can_edit"]


def test_board_locked_until_srs_approved(client, world):
    d = board(client, world, "s3", world["locked"])
    assert d["permissions"]["can_create"] is False and "unlocks once your SRS is approved" in d["permissions"]["reason"]
    r = add(client, world, "s3", world["locked"])
    assert r.status_code == 403 and "SRS is approved" in r.get_json()["message"]
    assert db.session.query(ScrumTask).count() == 0


def test_completed_project_board_is_read_only(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    world["team"].stage = "completed"
    db.session.commit()
    assert add(client, world, "s1", world["team"]).status_code == 403
    assert move(client, world, "s1", t["id"], "todo").status_code == 403
    assert client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"title": "x"}).status_code == 403


# ----------------------------------------------------------------------- create
def test_create_task_with_all_fields(client, world):
    sid = world["studs"]["s2"].id
    r = add(client, world, "s1", world["team"], "Design DB", description="ERD + migrations", priority="high",
            assigned_student_id=sid, start_date="2026-03-02", due_date="2026-03-09", status="todo")
    t = r.get_json()["data"]
    assert r.status_code == 201
    assert (t["title"], t["priority"], t["status"], t["position"]) == ("Design DB", "high", "todo", 0)
    assert t["assignee"]["student_id"] == sid and t["created_by"]["id"] == world["s1u"].id
    assert (t["start_date"], t["due_date"], t["completed_at"], t["version"]) == ("2026-03-02", "2026-03-09", None, 1)
    assert t["history"][0]["action"] == "created"
    # defaults: backlog + medium; positions append
    t2 = add(client, world, "s2", world["team"], "Second").get_json()["data"]
    t3 = add(client, world, "s2", world["team"], "Third").get_json()["data"]
    assert (t2["status"], t2["priority"]) == ("backlog", "medium") and t3["position"] == t2["position"] + 1


@pytest.mark.parametrize("payload,field", [
    ({"title": "   "}, "title"), ({"title": "x" * 256}, "title"), ({"title": "ok", "priority": "urgent"}, "priority"),
    ({"title": "ok", "status": "done"}, "status"), ({"title": "ok", "start_date": "garbage"}, "start_date"),
    ({"title": "ok", "start_date": "2026-03-10", "due_date": "2026-03-01"}, "due_date"),
    ({"title": "ok", "description": "x" * 5001}, "description"),
])
def test_task_validation(client, world, payload, field):
    r = client.post(f"/api/scrum/projects/{world['team'].id}/tasks", headers=world["H"]["s1"], json=payload)
    assert r.status_code == 422 and field in r.get_json()["errors"]
    assert db.session.query(ScrumTask).count() == 0


def test_assignee_must_be_project_member(client, world):
    outsider = world["studs"]["s4"].id
    r = add(client, world, "s1", world["team"], assigned_student_id=outsider)
    assert r.status_code == 422 and "assigned_student_id" in r.get_json()["errors"]


@pytest.mark.parametrize("who,code", [("s3", 404), ("s4", 404), ("m1", 403), ("la", 403), ("admin", 403)])
def test_only_project_students_create_tasks(client, world, who, code):
    assert add(client, world, who, world["team"]).status_code == code


# ------------------------------------------------------------------------- edit
def test_edit_task_records_history_and_bumps_version(client, world):
    t = add(client, world, "s1", world["team"], "Old", priority="low").get_json()["data"]
    sid = world["studs"]["s2"].id
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s2"],
                   json={"title": "New", "priority": "critical", "assigned_student_id": sid, "due_date": "2026-04-01", "version": 1})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["title"] == "New" and d["priority"] == "critical" and d["version"] == 2
    entries = {(h["action"], h["field"]): (h["old"], h["new"]) for h in d["history"]}
    assert entries[("updated", "title")] == ("Old", "New")
    assert entries[("updated", "priority")] == ("low", "critical")
    assert entries[("assigned", "assignee")] == (None, d["assignee"]["name"])
    assert entries[("updated", "due_date")] == (None, "2026-04-01")
    assert all(h["user"] for h in d["history"])


def test_edit_conflict_detected_by_version(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    assert client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"title": "A", "version": 1}).status_code == 200
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s2"], json={"title": "B", "version": 1})
    assert r.status_code == 409 and "changed by someone else" in r.get_json()["message"]


def test_unchanged_edit_adds_no_history(client, world):
    t = add(client, world, "s1", world["team"], "Same").get_json()["data"]
    client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"], json={"title": "Same"})
    assert db.session.query(ScrumTaskHistory).filter_by(task_id=t["id"]).count() == 1      # only 'created'


def test_edit_permissions_and_unassign(client, world):
    sid = world["studs"]["s1"].id
    t = add(client, world, "s1", world["team"], assigned_student_id=sid).get_json()["data"]
    for who, code in (("m1", 403), ("la", 403), ("s3", 404)):
        assert client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"][who], json={"title": "hack"}).status_code == code
    r = client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s2"], json={"assigned_student_id": None})
    assert r.get_json()["data"]["assignee"] is None


# --------------------------------------------------------------------- move/DnD
def test_move_between_columns_sets_completion_and_history(client, world):
    t = add(client, world, "s1", world["team"], "A").get_json()["data"]
    for status in ("todo", "in_progress", "in_review"):
        r = move(client, world, "s1", t["id"], status)
        assert r.status_code == 200
    d = client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"]).get_json()["data"]
    assert d["status"] == "in_review" and d["completed_at"] is None
    moves = [(h["old"], h["new"]) for h in reversed(d["history"]) if h["action"] == "moved"]
    assert moves == [("Backlog", "To Do"), ("To Do", "In Progress"), ("In Progress", "In Review")]
    move(client, world, "s1", t["id"], "completed")
    assert client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"]).get_json()["data"]["completed_at"]
    move(client, world, "s1", t["id"], "in_progress")                                  # reopened → completion cleared
    assert client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"]).get_json()["data"]["completed_at"] is None


def test_positions_are_resequenced_on_reorder_and_cross_column_moves(client, world):
    ids = [add(client, world, "s1", world["team"], f"T{i}").get_json()["data"]["id"] for i in range(4)]  # T0..T3 in backlog
    d = move(client, world, "s1", ids[3], "backlog", 0).get_json()["data"]
    assert titles(d, "backlog") == ["T3", "T0", "T1", "T2"]
    assert [t["position"] for t in col(d, "backlog")] == [0, 1, 2, 3]
    d = move(client, world, "s1", ids[0], "todo").get_json()["data"]                      # append to empty column
    assert titles(d, "backlog") == ["T3", "T1", "T2"] and [t["position"] for t in col(d, "backlog")] == [0, 1, 2]
    d = move(client, world, "s1", ids[2], "todo", 0).get_json()["data"]                    # insert at top of another column
    assert titles(d, "todo") == ["T2", "T0"]
    d = move(client, world, "s1", ids[1], "todo", 99).get_json()["data"]                  # out-of-range → clamps to end
    assert titles(d, "todo") == ["T2", "T0", "T1"]
    d = move(client, world, "s1", ids[1], "todo", -5).get_json()["data"]                  # negative → clamps to start
    assert titles(d, "todo")[0] == "T1"
    assert d["stats"]["by_status"] == {"backlog": 1, "todo": 3, "in_progress": 0, "in_review": 0, "completed": 0}


def test_invalid_move_target(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    assert move(client, world, "s1", t["id"], "nowhere").status_code == 422


def test_mentor_move_requires_lead_enabled_permission(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    assert move(client, world, "m1", t["id"], "todo").status_code == 403                  # default: view + comment only
    client.patch(f"/api/projects/{world['team'].id}/settings", headers=world["H"]["la"], json={"mentor_can_edit_board": True})
    assert move(client, world, "m1", t["id"], "todo").status_code == 200
    # even then the mentor still cannot create, edit or delete
    assert add(client, world, "m1", world["team"]).status_code == 403
    assert client.put(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["m1"], json={"title": "x"}).status_code == 403
    assert client.delete(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["m1"]).status_code == 403
    assert move(client, world, "m2", t["id"], "todo").status_code == 404                  # unassigned mentor
    assert move(client, world, "la", t["id"], "todo").status_code == 403


def test_move_to_in_review_notifies_mentors(client, world):
    t = add(client, world, "s1", world["team"], "Ship it").get_json()["data"]
    move(client, world, "s1", t["id"], "in_review")
    n = db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="task_in_review").one()
    assert "Ship it" in n.message and n.link == f"/scrum/{world['team'].id}"


# ------------------------------------------------------------------------ delete
def test_delete_only_before_work_starts_and_keeps_history(client, world):
    t1 = add(client, world, "s1", world["team"], "Backlog task").get_json()["data"]
    t2 = add(client, world, "s1", world["team"], "Started", status="in_progress").get_json()["data"]
    t3 = add(client, world, "s1", world["team"], "Todo task", status="todo").get_json()["data"]
    assert client.delete(f"/api/scrum/tasks/{t2['id']}", headers=world["H"]["s1"]).status_code == 409
    for t in (t1, t3):
        r = client.delete(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s2"])
        assert r.status_code == 200
    d = board(client, world, "s1", world["team"])
    assert d["stats"]["total"] == 1 and titles(d, "in_progress") == ["Started"]
    assert client.get(f"/api/scrum/tasks/{t1['id']}", headers=world["H"]["s1"]).status_code == 404   # hidden...
    row = db.session.get(ScrumTask, t1["id"])
    assert row.is_archived and db.session.query(ScrumTaskHistory).filter_by(task_id=t1["id"], action="deleted").count() == 1  # ...but kept
    assert client.delete(f"/api/scrum/tasks/{t1['id']}", headers=world["H"]["s1"]).status_code == 404


# ---------------------------------------------------------------------- comments
def test_comments_by_student_and_mentor_with_notifications(client, world):
    t = add(client, world, "s1", world["team"], "Commented").get_json()["data"]
    db.session.query(Notification).delete()
    db.session.commit()
    r = client.post(f"/api/scrum/tasks/{t['id']}/comments", headers=world["H"]["m1"], json={"body": "Please add tests"})
    assert r.status_code == 201
    assert {n.user_id for n in db.session.query(Notification).filter_by(type="task_comment")} == {world["s1u"].id, world["s2u"].id}
    client.post(f"/api/scrum/tasks/{t['id']}/comments", headers=world["H"]["s1"], json={"body": "Will do"})
    d = client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s2"]).get_json()["data"]
    assert [(c["user"], c["body"]) for c in d["comments"]][0][1] == "Please add tests" and len(d["comments"]) == 2
    assert d["comment_count"] == 2
    assert col(board(client, world, "s1", world["team"]), "backlog")[0]["comment_count"] == 2
    assert db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="task_comment").count() == 1


def test_comment_rules(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    url = f"/api/scrum/tasks/{t['id']}/comments"
    assert client.post(url, headers=world["H"]["s1"], json={"body": "   "}).status_code == 422
    assert client.post(url, headers=world["H"]["s1"], json={"body": "x" * 2001}).status_code == 422
    assert client.post(url, headers=world["H"]["la"], json={"body": "hi"}).status_code == 403     # leads are read-only
    assert client.post(url, headers=world["H"]["s3"], json={"body": "hi"}).status_code == 404
    assert client.post(url, headers=world["H"]["m2"], json={"body": "hi"}).status_code == 404
    assert client.post(url, headers=world["H"]["admin"], json={"body": "admin note"}).status_code == 201


def test_comment_text_is_stored_verbatim_not_executed(client, world):
    t = add(client, world, "s1", world["team"]).get_json()["data"]
    client.post(f"/api/scrum/tasks/{t['id']}/comments", headers=world["H"]["s1"], json={"body": "<script>alert(1)</script>"})
    d = client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s1"]).get_json()["data"]
    assert d["comments"][0]["body"] == "<script>alert(1)</script>"       # rendered as text by React


# ------------------------------------------------------------- isolation / stats
def test_tasks_are_isolated_between_projects(client, world):
    t = add(client, world, "s1", world["team"], "Private").get_json()["data"]
    add(client, world, "s4", world["other"], "Theirs")
    assert board(client, world, "s4", world["other"])["stats"]["total"] == 1
    for url, method in ((f"/api/scrum/tasks/{t['id']}", "get"),):
        assert client.get(url, headers=world["H"]["s4"]).status_code == 404
    assert move(client, world, "s4", t["id"], "todo").status_code == 404
    assert client.delete(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["s4"]).status_code == 404
    assert client.get(f"/api/scrum/tasks/{t['id']}", headers=world["H"]["lb"]).status_code == 404


def test_unauthenticated_requests_rejected(client, world):
    assert client.get(f"/api/scrum/projects/{world['team'].id}/board").status_code == 401
    assert client.post(f"/api/scrum/projects/{world['team'].id}/tasks", json={"title": "x"}).status_code == 401


def test_overdue_and_completion_stats(client, world):
    past = (date.today() - timedelta(days=3)).isoformat()
    future = (date.today() + timedelta(days=3)).isoformat()
    a = add(client, world, "s1", world["team"], "late", due_date=past).get_json()["data"]
    add(client, world, "s1", world["team"], "later", due_date=future)
    b = add(client, world, "s1", world["team"], "done-late", due_date=past).get_json()["data"]
    move(client, world, "s1", b["id"], "completed")
    d = board(client, world, "s1", world["team"])
    assert d["stats"]["overdue"] == 1 and d["stats"]["completed"] == 1 and d["stats"]["completion_pct"] == 33.3
    assert next(t for t in col(d, "backlog") if t["id"] == a["id"])["is_overdue"] is True
    assert col(d, "completed")[0]["is_overdue"] is False                              # finished tasks are never overdue
    # feeds the project's delayed flag and progress
    p = client.get(f"/api/projects/{world['team'].id}", headers=world["H"]["la"]).get_json()["data"]
    assert any("Scrum task" in r for r in p["delay_reasons"])


def test_scrum_progress_contribution(client, world):
    p = db.session.get(Project, world["team"].id)
    base = compute_progress(p)
    for i in range(4):
        t = add(client, world, "s1", world["team"], f"t{i}").get_json()["data"]
        if i < 2:
            move(client, world, "s1", t["id"], "completed")
    db.session.expire_all()
    assert compute_progress(db.session.get(Project, p.id)) == base + 12.5                  # 25% weight × 2/4


# --------------------------------------------------------------------- overview
def test_overview_scoped_for_monitoring(client, world):
    add(client, world, "s1", world["team"], "late", due_date=(date.today() - timedelta(days=1)).isoformat())
    add(client, world, "s4", world["other"], "x")
    get = lambda who, q="": client.get(f"/api/scrum/overview{q}", headers=world["H"][who]).get_json()  # noqa: E731
    assert get("m1")["meta"]["total"] == 3 and get("la")["meta"]["total"] == 3 and get("admin")["meta"]["total"] == 3
    assert get("m2")["meta"]["total"] == 0 and get("lb")["meta"]["total"] == 0
    only = get("m1", "?overdue=1")["data"]
    assert [i["title"] for i in only] == ["Project team"] and only[0]["stats"]["overdue"] == 1
    started = get("m1", "?started=1")["data"]
    assert {i["title"] for i in started} == {"Project team", "Project other"}             # locked project excluded
    assert client.get("/api/scrum/overview", headers=world["H"]["s1"]).status_code == 403


def test_board_created_lazily_for_legacy_projects(client, world):
    db.session.query(ScrumBoard).filter_by(project_id=world["team"].id).delete()
    db.session.commit()
    assert board(client, world, "s1", world["team"])["stats"]["total"] == 0
    assert add(client, world, "s1", world["team"]).status_code == 201
