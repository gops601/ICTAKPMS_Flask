"""The complete project lifecycle (20 steps) driven only through the public HTTP API.

`run(call, admin_email, admin_password, tag)` takes a `call(method, path, token=None, json=None, files=None)
-> (status, body)` function, so the exact same flow runs in the pytest suite (Flask test client) and against
a live deployment (requests). Every step asserts, so any workflow regression fails loudly.
"""

PDF = b"%PDF-1.4\n% SRS document\n"


def run(call, admin_email, admin_password, tag="x"):
    pw = "Passw0rd!x1"

    def ok(step, resp, expected=(200, 201)):
        status, body = resp
        assert status in expected, f"step {step}: HTTP {status} {body}"
        return body.get("data")

    def login(email, password):
        data = ok("login", call("POST", "/api/auth/login", json={"email": email, "password": password}))
        return data["access_token"], data["user"]

    admin, _ = login(admin_email, admin_password)

    # 1. Admin creates an OU (with an OU-specific batch field)
    ou = ok(1, call("POST", "/api/ous", admin, {"name": f"Flow OU {tag}", "code": f"FLOW{tag}".upper()[:30]}))
    ok(1, call("POST", f"/api/ous/{ou['id']}/fields", admin, {"label": "Programme", "is_required": True}))
    # 2. Admin creates a domain
    dom = ok(2, call("POST", "/api/domains", admin, {"name": f"Flow Domain {tag}", "code": f"FD{tag}".upper()[:30]}))
    other_dom = ok(2, call("POST", "/api/domains", admin, {"name": f"Other Domain {tag}", "code": f"OD{tag}".upper()[:30]}))
    # 3. Admin creates a batch (OU-specific fields validated)
    st, body = call("POST", "/api/batches", admin, {"code": f"FB-{tag}", "name": "Flow batch", "ou_id": ou["id"], "domain_id": other_dom["id"], "details": {}})
    assert st == 422, "required OU field must be enforced"
    batch = ok(3, call("POST", "/api/batches", admin, {"code": f"FB-{tag}", "name": "Flow batch", "ou_id": ou["id"],
                                                          "domain_id": other_dom["id"], "details": {"programme": "Full stack"}}))
    # 4. Admin assigns the batch to the domain
    batch = ok(4, call("PUT", f"/api/batches/{batch['id']}", admin, {"domain_id": dom["id"]}))
    assert batch["domain"]["id"] == dom["id"]

    # 5. Domain Lead logs in
    lead = ok(5, call("POST", "/api/admin/users", admin, {"role": "domain_lead", "name": "Flow Lead", "email": f"lead.{tag}@flow.test", "password": pw, "domain_ids": [dom["id"]]}))  # a lead is created with their domain
    lead_t, _ = login(f"lead.{tag}@flow.test", pw)
    # 6. Domain Lead adds a problem statement
    ps = ok(6, call("POST", "/api/problem-statements", lead_t, {"ps_code": f"FLOW-{tag}", "title": "Smart Attendance", "domain_id": dom["id"],
                                                                  "description": "<p>Build an attendance system</p>", "difficulty": "medium"}))
    # 7. Domain Lead assigns a mentor to the batch
    ok(7, call("POST", "/api/admin/users", admin, {"role": "mentor", "name": "Flow Mentor", "email": f"mentor.{tag}@flow.test", "password": pw, "domain_id": dom["id"]}))
    mentors = ok(7, call("GET", "/api/mentors", lead_t))
    mentor = next(m for m in mentors if m["email"] == f"mentor.{tag}@flow.test")
    # the mentor was created under the batch's domain, so they are on the batch automatically (no manual step)
    assert mentor["id"] in {m["id"] for m in ok(7, call("GET", f"/api/batches/{batch['id']}/mentors", lead_t))}
    stu = ok(7, call("POST", "/api/students", admin, {"name": "Flow Student", "email": f"stu.{tag}@flow.test", "registration_no": f"R-{tag}", "batch_id": batch["id"]}))
    # 8. Domain Lead allocates the project to the student
    projects = ok(8, call("POST", "/api/project-allocation", lead_t, {"batch_id": batch["id"], "items": [{"problem_statement_id": ps["id"], "student_ids": [stu["id"]]}]}))
    pid = projects[0]["id"]
    assert projects[0]["stage"] == "allocated"

    # 9. Student logs in (temporary password) and sees the project
    stu_t, stu_user = login(f"stu.{tag}@flow.test", stu["temporary_password"])
    assert stu_user["must_change_password"] is True
    mine = ok(9, call("GET", "/api/projects", stu_t))
    assert len(mine) == 1 and mine[0]["id"] == pid
    mentor_t, _ = login(f"mentor.{tag}@flow.test", pw)

    # 10. Student submits the SRS
    ok(10, call("POST", f"/api/projects/{pid}/transition", stu_t, {"to": "srs_preparation"}))
    st, _ = call("POST", f"/api/projects/{pid}/transition", stu_t, {"to": "implementation"})
    assert st == 409, "implementation must stay locked before SRS approval"
    srs = ok(10, call("POST", f"/api/srs/projects/{pid}", stu_t, files={"file": ("srs.pdf", PDF)}))
    sub_id = srs["submissions"][0]["id"]
    # 11. Mentor approves the SRS
    st, _ = call("POST", f"/api/srs/submissions/{sub_id}/review", mentor_t, {"decision": "request_changes"})
    assert st == 422, "comments are mandatory when requesting changes"
    ok(11, call("POST", f"/api/srs/submissions/{sub_id}/review", mentor_t, {"decision": "approve", "remarks": "Approved"}))
    # 12. Student adds the GitHub URL and starts implementation
    ok(12, call("POST", f"/api/projects/{pid}/transition", stu_t, {"to": "implementation"}))
    gh = ok(12, call("PUT", f"/api/github/projects/{pid}", stu_t, {"url": "https://github.com/flow/app.git", "description": "API + UI"}))
    assert gh["repository"]["url"] == "https://github.com/flow/app"

    # 13. Student creates Scrum tasks   14. Student updates task progress
    tasks = [ok(13, call("POST", f"/api/scrum/projects/{pid}/tasks", stu_t, {"title": f"Task {i}", "priority": "high"})) for i in range(3)]
    for t in tasks:
        for status in ("todo", "in_progress", "in_review", "completed"):
            ok(14, call("PATCH", f"/api/scrum/tasks/{t['id']}/move", stu_t, {"status": status}))
    # 15. Mentor views the Scrum board
    board = ok(15, call("GET", f"/api/scrum/projects/{pid}/board", mentor_t))
    assert board["stats"]["completed"] == 3 and board["permissions"]["can_comment"] and board["permissions"]["can_move"]  # mentors can change the board

    # 16. Mentor completes the Week 1 evaluation   17. Student views it
    reviews = ok(16, call("GET", f"/api/reviews/projects/{pid}", mentor_t))["reviews"]
    assert [r["week_no"] for r in reviews] == [1, 2, 3, 4]
    criteria = [{"name": "Problem Understanding", "max_marks": 20, "marks_obtained": 18}, {"name": "SRS Quality", "max_marks": 30, "marks_obtained": 25}]
    done = ok(16, call("POST", f"/api/reviews/{reviews[0]['id']}/submit", mentor_t,
                       {"criteria": criteria, "remarks": "Strong start", "strengths": "Clear scope", "improvements": "Add use cases"}))
    assert done["summary"] == {"total_obtained": 43.0, "total_max": 50.0, "percentage": 86.0, "criteria_count": 2, "scored_count": 2}
    seen = ok(17, call("GET", f"/api/reviews/{reviews[0]['id']}", stu_t))
    assert seen["visible"] and seen["summary"] is None and seen["improvements"] == "Add use cases"  # remarks only, no scores
    assert all("marks_obtained" not in c and "max_marks" not in c for c in seen["criteria"])
    hidden = ok(17, call("GET", f"/api/reviews/{reviews[1]['id']}", stu_t))
    assert hidden["visible"] is False

    # 18. Mentor completes Weeks 2, 3 and 4
    for r in reviews[1:]:
        ok(18, call("POST", f"/api/reviews/{r['id']}/submit", mentor_t, {"criteria": [{"name": f"Week {r['week_no']} work", "max_marks": 100, "marks_obtained": 80}], "remarks": "On track"}))
    overall = ok(18, call("GET", f"/api/reviews/projects/{pid}", stu_t))["overall"]
    assert overall == {"reviews_submitted": 4, "reviews_total": 4}   # students see progress, never scores

    # 19. Final evaluation is completed (needs all reviews + mandatory sign-off)
    st, _ = call("POST", f"/api/projects/{pid}/transition", mentor_t, {"to": "completed"})
    assert st == 409, "cannot complete before the final evaluation"
    ok(19, call("POST", f"/api/projects/{pid}/transition", mentor_t, {"to": "final_evaluation"}))
    st, _ = call("POST", f"/api/projects/{pid}/transition", mentor_t, {"to": "completed"})
    assert st == 409, "sign-off is mandatory"
    ok(19, call("POST", f"/api/reviews/projects/{pid}/final-signoff", mentor_t, {"remarks": "Excellent project"}))

    # 20. Project is marked as completed
    final = ok(20, call("POST", f"/api/projects/{pid}/transition", mentor_t, {"to": "completed"}))
    assert final["stage"] == "completed" and final["completed_at"]
    detail = ok(20, call("GET", f"/api/projects/{pid}", lead_t))
    assert detail["stage"] == "completed" and detail["progress"] >= 70 and detail["is_delayed"] is False
    timeline = ok(20, call("GET", f"/api/projects/{pid}/timeline", stu_t))
    stages = [i["to"] for i in reversed(timeline) if i["kind"] == "transition"]
    assert stages == ["allocated", "srs_preparation", "srs_submitted", "srs_approved", "implementation", "final_evaluation", "completed"]
    notes = ok(20, call("GET", "/api/notifications?per_page=50", stu_t))
    kinds = {n["type"] for n in notes}
    assert {"project_allocated", "srs_approved", "review_completed", "final_signed_off", "project_completed"} <= kinds
    return {"project_id": pid, "progress": detail["progress"], "stages": stages, "notifications": len(notes)}
