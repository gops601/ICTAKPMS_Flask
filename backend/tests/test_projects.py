from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (AuditLog, Batch, Domain, DomainLead, Mentor, Notification, OrganisationalUnit, ProblemStatement,
                        Project, ProjectLifecycleTransition, ProjectReview, ScrumBoard, ScrumTask, Student)
from app.services import lifecycle


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    """AIML batch B1 with 4 students, a mentor assigned? (no), second mentor, leads for AIML and IOT."""
    ou = db.session.query(OrganisationalUnit).first()
    admin = make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id),
                        DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    batch = Batch(code="B1", name="Batch 1", ou_id=ou.id, domain_id=domain("AIML").id)
    other = Batch(code="B2", name="Batch 2", ou_id=ou.id, domain_id=domain("IOT").id)
    db.session.add_all([batch, other])
    m1u, m2u, m3u = make_user("mentor", "m1@x.com"), make_user("mentor", "m2@x.com"), make_user("mentor", "m3@x.com")
    m1 = Mentor(user_id=m1u.id, domain_id=domain("AIML").id)
    m2 = Mentor(user_id=m2u.id, domain_id=None)
    m3 = Mentor(user_id=m3u.id, domain_id=domain("IOT").id)
    db.session.add_all([m1, m2, m3])
    students = []
    for i in range(1, 5):
        u = make_user("student", f"s{i}@x.com")
        db.session.flush()
        s = Student(user_id=u.id, batch_id=batch.id, registration_no=f"R{i}")
        db.session.add(s)
        students.append(s)
    ps = ProblemStatement(ps_code="PS1", title="Attendance", domain_id=domain("AIML").id, description="d")
    ps2 = ProblemStatement(ps_code="PS2", title="Chatbot", domain_id=domain("AIML").id, description="d")
    ps_off = ProblemStatement(ps_code="PS3", title="Off", domain_id=domain("AIML").id, description="d", status="inactive")
    ps_iot = ProblemStatement(ps_code="PS4", title="IoT", domain_id=domain("IOT").id, description="d")
    db.session.add_all([ps, ps2, ps_off, ps_iot])
    db.session.commit()
    H = {n: login(f"{e}@x.com") for n, e in [("admin", "admin"), ("la", "la"), ("lb", "lb"), ("m1", "m1"), ("m2", "m2"),
                                                ("m3", "m3"), ("s1", "s1"), ("s2", "s2"), ("s3", "s3")]}
    return dict(H=H, batch=batch, other=other, m1=m1, m2=m2, m3=m3, students=students, ps=ps, ps2=ps2, ps_off=ps_off,
                ps_iot=ps_iot, m1u=m1u, la=la)


def assign(client, world, mentor, who="la", batch=None):
    return client.post(f"/api/batches/{(batch or world['batch']).id}/mentors", headers=world["H"][who],
                       json={"mentor_id": mentor.id})


def allocate(client, world, student_idx, ps=None, team=False, who="la", **kw):
    body = {"batch_id": world["batch"].id,
            "items": [{"problem_statement_id": (ps or world["ps"]).id,
                       "student_ids": [world["students"][i].id for i in student_idx], "team": team}]}
    body.update(kw)
    return client.post("/api/project-allocation", headers=world["H"][who], json=body)


# ------------------------------------------------------------------ batch mentors
def test_assign_list_remove_batch_mentor(client, world):
    assert assign(client, world, world["m1"]).status_code == 201
    assert assign(client, world, world["m1"]).status_code == 409           # duplicate
    assert assign(client, world, world["m2"]).status_code == 201           # unassigned-domain mentor allowed
    assert assign(client, world, world["m3"]).status_code == 422           # different domain
    lst = client.get(f"/api/batches/{world['batch'].id}/mentors", headers=world["H"]["la"]).get_json()["data"]
    assert {m["email"] for m in lst} == {"m1@x.com", "m2@x.com"}
    assert client.delete(f"/api/batches/{world['batch'].id}/mentors/{world['m2'].id}", headers=world["H"]["la"]).status_code == 200
    assert client.delete(f"/api/batches/{world['batch'].id}/mentors/{world['m2'].id}", headers=world["H"]["la"]).status_code == 404
    # re-assigning a previously removed mentor reactivates the link
    assert assign(client, world, world["m2"]).status_code == 201


def test_mentor_assignment_is_domain_scoped_and_notifies(client, world):
    assert assign(client, world, world["m1"], who="lb").status_code == 404   # lead of another domain
    assert client.post(f"/api/batches/{world['batch'].id}/mentors", headers=world["H"]["m1"],
                       json={"mentor_id": world["m1"].id}).status_code == 403
    assign(client, world, world["m1"])
    assert db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="batch_assigned").count() == 1
    student_user = world["students"][0].user_id
    assert db.session.query(Notification).filter_by(user_id=student_user, type="mentor_assigned").count() == 1


def test_mentor_sees_only_assigned_batch(client, world):
    assert client.get(f"/api/batches/{world['batch'].id}", headers=world["H"]["m1"]).status_code == 404
    assign(client, world, world["m1"])
    assert client.get(f"/api/batches/{world['batch'].id}", headers=world["H"]["m1"]).status_code == 200
    assert client.get(f"/api/students?batch_id={world['batch'].id}", headers=world["H"]["m1"]).get_json()["meta"]["total"] == 4


def test_reassign_batch_mentor_moves_overrides(client, world):
    assign(client, world, world["m1"])
    assign(client, world, world["m2"])
    pid = allocate(client, world, [0], mentor_id=world["m1"].id).get_json()["data"][0]["id"]
    assert db.session.get(Project, pid).mentor_id == world["m1"].id
    r = client.post(f"/api/batches/{world['batch'].id}/mentors/{world['m1'].id}/reassign", headers=world["H"]["la"],
                    json={"to_mentor_id": world["m2"].id})
    assert r.status_code == 200
    assert {m["email"] for m in r.get_json()["data"]} == {"m2@x.com"}
    assert db.session.get(Project, pid).mentor_id == world["m2"].id
    assert client.get(f"/api/projects/{pid}", headers=world["H"]["m1"]).status_code == 404   # old mentor lost access
    assert client.get(f"/api/projects/{pid}", headers=world["H"]["m2"]).status_code == 200
    # same mentor / non-assigned source are rejected
    assert client.post(f"/api/batches/{world['batch'].id}/mentors/{world['m2'].id}/reassign", headers=world["H"]["la"],
                       json={"to_mentor_id": world["m2"].id}).status_code == 422
    assert client.post(f"/api/batches/{world['batch'].id}/mentors/{world['m1'].id}/reassign", headers=world["H"]["la"],
                       json={"to_mentor_id": world["m2"].id}).status_code == 404


def test_removing_mentor_clears_project_override(client, world):
    assign(client, world, world["m1"])
    pid = allocate(client, world, [0], mentor_id=world["m1"].id).get_json()["data"][0]["id"]
    client.delete(f"/api/batches/{world['batch'].id}/mentors/{world['m1'].id}", headers=world["H"]["la"])
    assert db.session.get(Project, pid).mentor_id is None


def test_mentor_list_scoped_for_lead_with_workload(client, world):
    assign(client, world, world["m1"])
    allocate(client, world, [0, 1])
    ms = {m["email"]: m for m in client.get("/api/mentors", headers=world["H"]["la"]).get_json()["data"]}
    assert set(ms) == {"m1@x.com", "m2@x.com"}                      # AIML mentor + domain-less mentor, not IOT's
    assert ms["m1@x.com"]["batch_count"] == 1 and ms["m1@x.com"]["project_count"] == 2
    assert ms["m2@x.com"]["project_count"] == 0
    assert len(client.get("/api/mentors", headers=world["H"]["admin"]).get_json()["data"]) == 3


# ---------------------------------------------------------------------- allocation
def test_individual_allocation_creates_full_project_scaffolding(client, world):
    assign(client, world, world["m1"])
    r = allocate(client, world, [0, 1, 2], start_date="2026-03-02")
    data = r.get_json()["data"]
    assert r.status_code == 201 and len(data) == 3 and {p["stage"] for p in data} == {"allocated"}
    p = db.session.get(Project, data[0]["id"])
    assert p.title == "Attendance" and p.start_date == date(2026, 3, 2) and p.target_end_date == date(2026, 3, 30)
    assert db.session.query(ScrumBoard).filter_by(project_id=p.id).count() == 1
    reviews = db.session.query(ProjectReview).filter_by(project_id=p.id).order_by(ProjectReview.week_no).all()
    assert [r_.due_date for r_ in reviews] == [date(2026, 3, 9), date(2026, 3, 16), date(2026, 3, 23), date(2026, 3, 30)]
    assert db.session.query(ProjectLifecycleTransition).filter_by(project_id=p.id, to_stage="allocated").count() == 1
    assert len(data[0]["members"]) == 1 and data[0]["mentors"][0]["name"]


def test_team_allocation_one_project_many_students(client, world):
    r = allocate(client, world, [0, 1], team=True)
    d = r.get_json()["data"]
    assert len(d) == 1 and len(d[0]["members"]) == 2 and d[0]["members"][0]["is_lead"] is True


def test_allocation_notifies_students_mentors_and_leads(client, world):
    assign(client, world, world["m1"])
    db.session.query(Notification).delete()
    db.session.commit()
    allocate(client, world, [0])
    kinds = lambda uid: {n.type for n in db.session.query(Notification).filter_by(user_id=uid)}  # noqa: E731
    assert "project_allocated" in kinds(world["students"][0].user_id)
    assert "project_allocated" in kinds(world["m1u"].id)
    assert "projects_allocated" in kinds(world["la"].id)
    assert not kinds(world["students"][1].user_id)


def test_allocation_validation_rules(client, world):
    # student already has a project
    allocate(client, world, [0])
    r = allocate(client, world, [0], ps=world["ps2"])
    assert r.status_code == 422 and "already has a project" in r.get_json()["message"]
    assert db.session.query(Project).count() == 1
    # domain mismatch, inactive statement
    assert allocate(client, world, [1], ps=world["ps_iot"]).status_code == 422
    assert allocate(client, world, [1], ps=world["ps_off"]).status_code == 422
    # student from another batch
    other_u = db.session.query(Student).filter_by(registration_no="R4").one()
    other_u.batch_id = world["other"].id
    db.session.commit()
    assert allocate(client, world, [3]).status_code == 422
    # mentor not assigned to the batch
    assert allocate(client, world, [1], mentor_id=world["m1"].id).status_code == 422
    # same student twice
    body = {"batch_id": world["batch"].id, "items": [
        {"problem_statement_id": world["ps"].id, "student_ids": [world["students"][1].id]},
        {"problem_statement_id": world["ps2"].id, "student_ids": [world["students"][1].id]}]}
    assert client.post("/api/project-allocation", headers=world["H"]["la"], json=body).status_code == 422
    assert allocate(client, world, []).status_code == 422
    # none of the failures created anything beyond the first project
    assert db.session.query(Project).count() == 1


def test_allocation_is_atomic(client, world):
    body = {"batch_id": world["batch"].id, "items": [
        {"problem_statement_id": world["ps"].id, "student_ids": [world["students"][0].id]},
        {"problem_statement_id": world["ps_iot"].id, "student_ids": [world["students"][1].id]}]}   # second item invalid
    assert client.post("/api/project-allocation", headers=world["H"]["la"], json=body).status_code == 422
    db.session.rollback()
    assert db.session.query(Project).count() == 0


def test_allocation_permissions(client, world):
    assert allocate(client, world, [0], who="lb").status_code == 404        # other domain's lead
    assert allocate(client, world, [0], who="m1").status_code == 403
    assert allocate(client, world, [0], who="s1").status_code == 403
    assert allocate(client, world, [0], who="admin").status_code == 201
    world["batch"].status = "closed"
    db.session.commit()
    assert allocate(client, world, [1]).status_code == 409


def test_reassign_problem_statement_rules(client, world):
    pid = allocate(client, world, [0]).get_json()["data"][0]["id"]
    h = world["H"]["la"]
    r = client.post(f"/api/projects/{pid}/reassign-problem", headers=h, json={"problem_statement_id": world["ps2"].id})
    assert r.status_code == 200 and r.get_json()["data"]["title"] == "Chatbot"
    assert client.post(f"/api/projects/{pid}/reassign-problem", headers=h, json={"problem_statement_id": world["ps2"].id}).status_code == 409
    assert client.post(f"/api/projects/{pid}/reassign-problem", headers=h, json={"problem_statement_id": world["ps_iot"].id}).status_code == 422
    db.session.get(Project, pid).stage = "srs_submitted"
    db.session.commit()
    assert client.post(f"/api/projects/{pid}/reassign-problem", headers=h, json={"problem_statement_id": world["ps"].id}).status_code == 409


# ------------------------------------------------------------------------- listing
def test_project_listing_is_scoped(client, world):
    assign(client, world, world["m1"])
    allocate(client, world, [0, 1])
    count = lambda who: client.get("/api/projects", headers=world["H"][who]).get_json()["meta"]["total"]  # noqa: E731
    assert (count("admin"), count("la"), count("lb"), count("m1"), count("m2")) == (2, 2, 0, 2, 0)
    assert count("s1") == 1 and count("s3") == 0
    pid = client.get("/api/projects", headers=world["H"]["s1"]).get_json()["data"][0]["id"]
    assert client.get(f"/api/projects/{pid}", headers=world["H"]["s3"]).status_code == 404
    assert client.get(f"/api/projects/{pid}", headers=world["H"]["lb"]).status_code == 404
    assert client.get("/api/projects?q=R1", headers=world["H"]["la"]).get_json()["meta"]["total"] == 1
    assert client.get("/api/projects?stage=completed", headers=world["H"]["la"]).get_json()["meta"]["total"] == 0


def test_student_list_shows_project_summary(client, world):
    allocate(client, world, [0])
    rows = client.get(f"/api/students?batch_id={world['batch'].id}&sort=registration_no", headers=world["H"]["la"]).get_json()["data"]
    assert rows[0]["project"]["stage"] == "allocated" and rows[1]["project"] is None


# --------------------------------------------------------------------- lifecycle
def pid_for(client, world, idx=0):
    return allocate(client, world, [idx]).get_json()["data"][0]["id"]


def go(client, world, pid, who, to, reason=None):
    return client.post(f"/api/projects/{pid}/transition", headers=world["H"][who], json={"to": to, "reason": reason})


def force(pid, stage, **kw):
    p = db.session.get(Project, pid)
    p.stage = stage
    for k, v in kw.items():
        setattr(p, k, v)
    db.session.commit()


def submit_reviews(pid, n=4):
    for r in db.session.query(ProjectReview).filter_by(project_id=pid).all():
        if r.week_no <= n:
            r.status = "submitted"
    db.session.commit()


def test_student_starts_srs_preparation_but_cannot_skip_ahead(client, world):
    assign(client, world, world["m1"])
    pid = pid_for(client, world)
    assert go(client, world, pid, "s1", "implementation").status_code == 409        # cannot skip SRS
    assert go(client, world, pid, "s1", "srs_approved").status_code == 409          # cannot self-approve
    assert go(client, world, pid, "s1", "completed").status_code == 409
    assert go(client, world, pid, "m1", "srs_preparation").status_code == 403       # mentors don't start it
    assert go(client, world, pid, "s1", "srs_preparation").status_code == 200
    assert go(client, world, pid, "s1", "srs_preparation").status_code == 409       # not repeatable
    # SRS steps are system-driven only, even for the admin
    assert go(client, world, pid, "s1", "srs_submitted").status_code == 409
    assert go(client, world, pid, "admin", "srs_submitted").status_code == 409


def test_other_students_and_leads_cannot_transition(client, world):
    pid = pid_for(client, world)
    assert go(client, world, pid, "s3", "srs_preparation").status_code == 404
    assert go(client, world, pid, "lb", "srs_preparation").status_code == 404


def test_implementation_requires_srs_approval(client, world):
    pid = pid_for(client, world)
    force(pid, "srs_under_review")
    assert go(client, world, pid, "s1", "implementation").status_code == 409
    force(pid, "srs_approved")
    r = go(client, world, pid, "s1", "implementation")
    assert r.status_code == 200 and r.get_json()["data"]["stage"] == "implementation"
    assert db.session.get(Project, pid).implementation_started_at is not None


def test_system_transitions_follow_the_state_machine(client, world, app):
    pid = pid_for(client, world)
    student = world["students"][0].user
    mentor_user = world["m1u"]
    p = db.session.get(Project, pid)
    lifecycle.transition(p, "srs_preparation", student)
    lifecycle.transition(p, "srs_submitted", student, system=True)
    lifecycle.transition(p, "srs_changes_requested", mentor_user, system=True)
    lifecycle.transition(p, "srs_submitted", student, system=True)
    lifecycle.transition(p, "srs_under_review", mentor_user, system=True)
    lifecycle.transition(p, "srs_approved", mentor_user, system=True)
    db.session.commit()
    assert p.stage == "srs_approved"
    stages = [t.to_stage for t in db.session.query(ProjectLifecycleTransition).filter_by(project_id=pid).order_by(ProjectLifecycleTransition.id)]
    assert stages == ["allocated", "srs_preparation", "srs_submitted", "srs_changes_requested", "srs_submitted",
                      "srs_under_review", "srs_approved"]
    assert all(t.created_at for t in db.session.query(ProjectLifecycleTransition).filter_by(project_id=pid))


def test_final_evaluation_and_completion_guards(client, world):
    assign(client, world, world["m1"])
    pid = pid_for(client, world)
    force(pid, "implementation")
    assert go(client, world, pid, "s1", "final_evaluation").status_code == 403       # students can't
    r = go(client, world, pid, "m1", "final_evaluation")
    assert r.status_code == 409 and "four weekly reviews" in r.get_json()["message"]
    actions = client.get(f"/api/projects/{pid}", headers=world["H"]["m1"]).get_json()["data"]["available_actions"]
    assert actions == [{"to": "final_evaluation", "label": "Final Evaluation", "enabled": False,
                        "reason": "All four weekly reviews must be submitted before the final evaluation"}]
    submit_reviews(pid, 3)
    assert go(client, world, pid, "m1", "final_evaluation").status_code == 409       # only 3 of 4
    submit_reviews(pid, 4)
    assert go(client, world, pid, "m1", "final_evaluation").status_code == 200
    # completion also needs the mandatory final sign-off
    r = go(client, world, pid, "m1", "completed")
    assert r.status_code == 409 and "sign-off" in r.get_json()["message"]
    force(pid, "final_evaluation", final_signed_off_by=world["m1u"].id)
    r = go(client, world, pid, "m1", "completed")
    assert r.status_code == 200 and r.get_json()["data"]["completed_at"]
    assert go(client, world, pid, "m1", "implementation").status_code == 409         # completed is terminal


def test_mentor_cannot_touch_unassigned_project(client, world):
    assign(client, world, world["m1"])
    pid = pid_for(client, world)
    force(pid, "implementation")
    assert go(client, world, pid, "m2", "final_evaluation").status_code == 404


def test_reopen_is_admin_only_audited_and_notifies(client, world):
    assign(client, world, world["m1"])
    pid = pid_for(client, world)
    submit_reviews(pid)
    force(pid, "completed", final_signed_off_by=world["m1u"].id, completed_at=db.session.get(Project, pid).created_at)
    body = {"to": "implementation", "reason": "Marks need correction"}
    for who in ("la", "m1", "s1"):
        assert client.post(f"/api/projects/{pid}/reopen", headers=world["H"][who], json=body).status_code == 403
    h = world["H"]["admin"]
    assert client.post(f"/api/projects/{pid}/reopen", headers=h, json={"to": "implementation", "reason": "x"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/reopen", headers=h, json={"to": "completed", "reason": "Because"}).status_code == 422
    db.session.query(Notification).delete()
    db.session.commit()
    r = client.post(f"/api/projects/{pid}/reopen", headers=h, json=body)
    assert r.status_code == 200 and r.get_json()["data"]["stage"] == "implementation"
    p = db.session.get(Project, pid)
    assert p.completed_at is None and p.final_signed_off_by is None
    t = db.session.query(ProjectLifecycleTransition).filter_by(project_id=pid, is_reopen=True).one()
    assert t.reason == "Marks need correction" and t.from_stage == "completed"
    assert db.session.query(AuditLog).filter_by(action="project.reopen", entity_id=pid).count() == 1
    assert {n.type for n in db.session.query(Notification)} == {"project_reopened"}
    # cannot "reopen" forwards
    assert client.post(f"/api/projects/{pid}/reopen", headers=h, json={"to": "final_evaluation", "reason": "Forward?"}).status_code == 409


def test_timeline_lists_transitions_and_activity(client, world):
    pid = pid_for(client, world)
    go(client, world, pid, "s1", "srs_preparation", "starting")
    client.post(f"/api/projects/{pid}/reassign-problem", headers=world["H"]["la"], json={"problem_statement_id": world["ps2"].id})
    tl = client.get(f"/api/projects/{pid}/timeline", headers=world["H"]["s1"]).get_json()["data"]
    kinds = [(i["kind"], i.get("to") or i.get("action")) for i in tl]
    assert ("transition", "srs_preparation") in kinds and ("transition", "allocated") in kinds
    assert ("activity", "problem_statement.changed") in kinds
    assert tl[0]["at"] >= tl[-1]["at"]
    assert client.get(f"/api/projects/{pid}/timeline", headers=world["H"]["s3"]).status_code == 404


def test_board_permission_toggle_is_lead_only(client, world):
    pid = pid_for(client, world)
    assert client.patch(f"/api/projects/{pid}/settings", headers=world["H"]["s1"], json={"mentor_can_edit_board": True}).status_code == 403
    r = client.patch(f"/api/projects/{pid}/settings", headers=world["H"]["la"], json={"mentor_can_edit_board": True})
    assert r.status_code == 200 and r.get_json()["data"]["mentor_can_edit_board"] is True


def test_project_level_mentor_override(client, world):
    assign(client, world, world["m1"])
    assign(client, world, world["m2"])
    pid = pid_for(client, world)
    r = client.put(f"/api/projects/{pid}/mentor", headers=world["H"]["la"], json={"mentor_id": world["m2"].id})
    assert [m["id"] for m in r.get_json()["data"]["mentors"]] == [world["m2"].id]
    assert client.get(f"/api/projects/{pid}", headers=world["H"]["m1"]).status_code == 200   # still a batch mentor of B1
    r = client.put(f"/api/projects/{pid}/mentor", headers=world["H"]["la"], json={"mentor_id": None})
    assert {m["id"] for m in r.get_json()["data"]["mentors"]} == {world["m1"].id, world["m2"].id}
    assert client.put(f"/api/projects/{pid}/mentor", headers=world["H"]["la"], json={"mentor_id": world["m3"].id}).status_code == 422


# --------------------------------------------------------------- progress / delay
def test_progress_and_delay_calculation(client, world):
    pid = pid_for(client, world)
    p = db.session.get(Project, pid)
    from app.services.project_service import compute_progress, delay_reasons
    assert compute_progress(p) == 0
    p.stage = "srs_approved"
    db.session.commit()
    assert compute_progress(p) == 20
    board = db.session.query(ScrumBoard).filter_by(project_id=pid).one()
    db.session.add_all([ScrumTask(board_id=board.id, title="a", status="completed"),
                        ScrumTask(board_id=board.id, title="b", status="todo")])
    submit_reviews(pid, 2)
    assert compute_progress(p) == 20 + 12.5 + 20
    # delay: a fresh project is on track, an old unreviewed one is not
    p.start_date = date.today() - timedelta(weeks=5)
    for r in db.session.query(ProjectReview).filter_by(project_id=pid):
        r.due_date = p.start_date + timedelta(weeks=r.week_no)
    db.session.commit()
    reasons = delay_reasons(p)
    assert any("review" in r for r in reasons)
    p.stage = "completed"
    assert delay_reasons(p) == []
    listing = client.get("/api/projects?delayed=1", headers=world["H"]["la"]).get_json()
    assert listing["meta"]["total"] >= 0


def test_configurable_progress_weights(client, world):
    from app.models import SystemSetting
    from app.services.project_service import compute_progress
    pid = pid_for(client, world)
    p = db.session.get(Project, pid)
    p.stage = "srs_approved"
    db.session.add(SystemSetting(key="progress_weights", value={"srs": 50, "github": 0, "scrum": 0, "reviews": 50, "final": 0}))
    db.session.commit()
    assert compute_progress(p) == 50


# ---------------------------------------------------------------- notifications
def test_notifications_api(client, world):
    assign(client, world, world["m1"])
    allocate(client, world, [0])
    h = world["H"]["s1"]
    r = client.get("/api/notifications", headers=h).get_json()
    assert r["meta"]["total"] == 2                      # mentor assigned + project allocated
    assert client.get("/api/notifications/unread-count", headers=h).get_json()["data"]["count"] == 2
    nid = r["data"][0]["id"]
    assert client.post(f"/api/notifications/{nid}/read", headers=h).status_code == 200
    assert client.get("/api/notifications/unread-count", headers=h).get_json()["data"]["count"] == 1
    assert client.get("/api/notifications?unread=1", headers=h).get_json()["meta"]["total"] == 1
    # cannot touch someone else's notification
    assert client.post(f"/api/notifications/{nid}/read", headers=world["H"]["s2"]).status_code == 404
    assert client.get("/api/notifications", headers=world["H"]["s2"]).get_json()["meta"]["total"] == 1  # only the batch-mentor one
    assert client.post("/api/notifications/read-all", headers=h).status_code == 200
    assert client.get("/api/notifications/unread-count", headers=h).get_json()["data"]["count"] == 0
    assert client.get("/api/notifications").status_code == 401


def test_admin_assigning_batch_to_domain_notifies_the_lead(client, world):
    db.session.query(Notification).delete()
    db.session.commit()
    h = world["H"]["admin"]
    ou = db.session.query(OrganisationalUnit).filter_by(code="RETAIL").one()
    body = {"code": "NB-1", "name": "New", "ou_id": ou.id, "domain_id": domain("AIML").id, "details": {"programme_name": "P"}}
    assert client.post("/api/batches", headers=h, json=body).status_code == 201
    assert db.session.query(Notification).filter_by(user_id=world["la"].id, type="batch_assigned").count() == 1
    bid = db.session.query(Batch).filter_by(code="NB-1").one().id
    client.put(f"/api/batches/{bid}", headers=h, json={"domain_id": domain("IOT").id})
    lb = db.session.query(DomainLead).filter_by(domain_id=domain("IOT").id).one().user_id
    assert db.session.query(Notification).filter_by(user_id=lb, type="batch_assigned").count() == 1
