import io
import json

import pytest

from app.extensions import db
from app.models import (Batch, BatchMentor, Domain, DomainLead, Mentor, OrganisationalUnit, Project, ProjectStudent, ScrumBoard,
                        ScrumTask, ScrumTaskAssignee, Student, StudentProposal, User)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    ou = db.session.query(OrganisationalUnit).first()
    make_user("admin", "admin@x.com")
    lead = make_user("domain_lead", "lead@x.com")
    lead_b = make_user("domain_lead", "leadb@x.com")
    db.session.add_all([DomainLead(user_id=lead.id, domain_id=domain("AIML").id), DomainLead(user_id=lead_b.id, domain_id=domain("IOT").id)])
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    other = Batch(code="B2", name="Other", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add_all([batch, other])
    m1u, m2u = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com")
    m1, m2 = Mentor(user_id=m1u.id, domain_id=domain("AIML").id), Mentor(user_id=m2u.id, domain_id=domain("AIML").id)
    db.session.add_all([m1, m2])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m1.id))
    db.session.add(BatchMentor(batch_id=other.id, mentor_id=m2.id))
    studs = {}
    for n in ("s1", "s2", "s3", "s4"):
        u = make_user("student", f"{n}@x.com")
        db.session.flush()
        studs[n] = Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper())
        db.session.add(studs[n])
    ou_ = make_user("student", "out@x.com")
    db.session.flush()
    studs["out"] = Student(user_id=ou_.id, batch_id=other.id, registration_no="OUT")
    db.session.add(studs["out"])
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "lead", "leadb", "m1", "m2", "s1", "s2", "s3", "s4", "out")}
    return dict(H=H, batch=batch, studs=studs, m1=m1)


def propose(client, world, who="s1", mode="individual", members=None, title="Smart Campus"):
    data = {"title": title, "summary": "Campus app", "file": (io.BytesIO(PDF), "detail.pdf"), "project_mode": mode}
    if members is not None:
        data["members"] = json.dumps(members)
    return client.post("/api/proposals", headers=world["H"][who], content_type="multipart/form-data", data=data)


def sid(world, n):
    return world["studs"][n].id


# ------------------------------------------------------------ the student's individual / group choice
def test_classmates_lists_only_free_batch_mates(client, world):
    d = client.get("/api/proposals/classmates", headers=world["H"]["s1"]).get_json()["data"]
    assert sorted(s["registration_no"] for s in d["students"]) == ["S2", "S3", "S4"] and d["max_group_size"] == 6   # not self, not another batch
    assert client.get("/api/proposals/classmates", headers=world["H"]["m1"]).status_code == 403


def test_group_proposal_needs_classmates_and_valid_members(client, world):
    assert propose(client, world, mode="group", members=[]).status_code == 422                     # nobody else selected
    assert propose(client, world, mode="group", members=[{"student_id": sid(world, "out")}]).status_code == 422   # other batch
    assert propose(client, world, mode="group", members=[{"student_id": sid(world, "s2")}] * 1 + [{"student_id": 9999}]).status_code == 422
    assert propose(client, world, mode="sideways").status_code == 422
    assert db.session.query(StudentProposal).count() == 0
    many = [{"student_id": sid(world, n)} for n in ("s2", "s3", "s4")] + [{"student_id": 9990 + i} for i in range(3)]
    assert propose(client, world, mode="group", members=many).status_code == 422                   # too large / unknown


def test_group_proposal_roles_shelf_and_notifications(client, world):
    r = propose(client, world, mode="group", members=[{"student_id": sid(world, "s2"), "role": "Backend"},
                                                      {"student_id": sid(world, "s3"), "role": ""}])
    assert r.status_code == 201, r.get_json()
    d = r.get_json()["data"]
    assert d["is_group"] and len(d["members"]) == 3
    assert d["members"][0]["role"] == "Team Lead" and d["members"][1]["role"] == "Backend"
    # the picked classmates are told, and cannot start or join anything else meanwhile
    info = client.get("/api/proposals/mine", headers=world["H"]["s2"]).get_json()["data"]
    assert info["can_upload"] is False and "added you to the group project" in info["blocked_reason"]
    assert propose(client, world, who="s2", title="Mine too").status_code == 409
    free = {s["registration_no"] for s in client.get("/api/proposals/classmates", headers=world["H"]["s4"]).get_json()["data"]["students"]}
    assert free == set()                                                                           # S1-S3 are tied up in the group
    # the group is visible to the mentor on the shelf entry
    ps_id = d["shelf"]["id"]
    shelf = client.get(f"/api/problem-statements/{ps_id}", headers=world["H"]["m1"]).get_json()["data"]
    assert shelf["proposal"]["is_group"] and len(shelf["proposal"]["members"]) == 3 and shelf["approval_status"] == "pending"


def test_mentor_approves_group_from_the_shelf_and_everyone_gets_the_project(client, world):
    d = propose(client, world, mode="group", members=[{"student_id": sid(world, "s2"), "role": "Frontend"}]).get_json()["data"]
    ps_id = d["shelf"]["id"]
    r = client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"]["m1"], json={"decision": "approve"})
    assert r.status_code == 200, r.get_json()
    p = db.session.query(Project).one()
    assert p.stage == "srs_preparation" and {m.student_id for m in p.members} == {sid(world, "s1"), sid(world, "s2")}
    roles = {m.student_id: (m.role, m.is_lead) for m in p.members}
    assert roles[sid(world, "s1")] == ("Team Lead", True) and roles[sid(world, "s2")] == ("Frontend", False)
    for who in ("s1", "s2"):
        proj = client.get(f"/api/projects/{p.id}", headers=world["H"][who]).get_json()["data"]
        assert sorted(m["role"] for m in proj["members"]) == ["Frontend", "Team Lead"]
    assert client.get(f"/api/projects/{p.id}", headers=world["H"]["s3"]).status_code == 404


@pytest.mark.parametrize("who,code", [("lead", 200), ("admin", 200), ("m1", 200), ("m2", 404), ("leadb", 404)])
def test_who_may_review_from_the_shelf(client, world, who, code):
    ps_id = propose(client, world).get_json()["data"]["shelf"]["id"]
    r = client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"][who], json={"decision": "approve"})
    assert r.status_code == code, r.get_json()


def test_students_cannot_review_and_reject_needs_remarks(client, world):
    ps_id = propose(client, world).get_json()["data"]["shelf"]["id"]
    assert client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"]["s1"], json={"decision": "approve"}).status_code == 403
    assert client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"]["lead"], json={"decision": "reject"}).status_code == 422
    r = client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"]["lead"], json={"decision": "reject", "remarks": "Too broad"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "rejected"
    # after a rejection the group is free again
    assert propose(client, world, who="s2", title="Fresh start").status_code == 201


# ------------------------------------------------------------ only mentors / leads change the group
@pytest.fixture()
def team(client, world):
    ps_id = propose(client, world, mode="group", members=[{"student_id": sid(world, "s2"), "role": "Backend"}]).get_json()["data"]["shelf"]["id"]
    client.post(f"/api/proposals/shelf/{ps_id}/review", headers=world["H"]["m1"], json={"decision": "approve"})
    return db.session.query(Project).one()


def put_members(client, world, who, project, members, reason=None):
    return client.put(f"/api/projects/{project.id}/members", headers=world["H"][who], json={"members": members, "reason": reason})


@pytest.mark.parametrize("who", ["s1", "s2", "s3"])
def test_students_cannot_change_the_group(client, world, team, who):
    r = put_members(client, world, who, team, [{"student_id": sid(world, "s1")}])
    assert r.status_code == 403


@pytest.mark.parametrize("who,code", [("m1", 200), ("lead", 200), ("admin", 200), ("m2", 404), ("leadb", 404)])
def test_mentor_lead_and_admin_can_change_the_group(client, world, team, who, code):
    r = put_members(client, world, who, team, [{"student_id": sid(world, "s1"), "role": "Lead", "is_lead": True},
                                               {"student_id": sid(world, "s3"), "role": "Tester"}], "s2 moved")
    assert r.status_code == code, r.get_json()
    if code == 200:
        got = {m["student_id"]: (m["role"], m["is_lead"]) for m in r.get_json()["data"]["members"]}
        assert got == {sid(world, "s1"): ("Lead", True), sid(world, "s3"): ("Tester", False)}


def test_group_change_rules_and_scrum_cleanup(client, world, team):
    # a task assigned to s2 loses the assignment when s2 leaves the group
    board = db.session.query(ScrumBoard).filter_by(project_id=team.id).first() or ScrumBoard(project_id=team.id)
    db.session.add(board)
    db.session.flush()
    t = ScrumTask(board_id=board.id, title="API", assigned_student_id=sid(world, "s2"))
    db.session.add(t)
    db.session.flush()
    db.session.add(ScrumTaskAssignee(task_id=t.id, student_id=sid(world, "s2")))
    db.session.commit()
    assert put_members(client, world, "m1", team, []).status_code == 422                            # needs one student
    assert put_members(client, world, "m1", team, [{"student_id": sid(world, "out")}]).status_code == 422      # other batch
    assert put_members(client, world, "m1", team, [{"student_id": sid(world, "s1")}, {"student_id": sid(world, "s1")}]).status_code == 422
    r = put_members(client, world, "m1", team, [{"student_id": sid(world, "s1"), "role": "Solo"}])
    assert r.status_code == 200 and [m["student_id"] for m in r.get_json()["data"]["members"]] == [sid(world, "s1")]
    assert db.session.query(ScrumTaskAssignee).filter_by(task_id=t.id).count() == 0
    assert db.session.get(ScrumTask, t.id).assigned_student_id is None
    assert client.get(f"/api/projects/{team.id}", headers=world["H"]["s2"]).status_code == 404       # s2 no longer sees it
    # a student who already has a project elsewhere cannot be added
    other = Project(batch_id=world["batch"].id, problem_statement_id=team.problem_statement_id, title="X", stage="allocated")
    db.session.add(other)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=other.id, student_id=sid(world, "s4")))
    db.session.commit()
    assert put_members(client, world, "m1", team, [{"student_id": sid(world, "s1")}, {"student_id": sid(world, "s4")}]).status_code == 422


def test_scrum_board_shows_member_roles(client, world, team):
    d = client.get(f"/api/scrum/projects/{team.id}/board", headers=world["H"]["s1"]).get_json()["data"]
    assert {(m["student_id"], m["role"], m["is_lead"]) for m in d["members"]} == {(sid(world, "s1"), "Team Lead", True), (sid(world, "s2"), "Backend", False)}
