import io
import os

import pytest

from app.extensions import db
from app.models import (AuditLog, Batch, BatchMentor, Domain, DomainLead, FileAttachment, Mentor, Notification,
                        OrganisationalUnit, ProblemStatement, Project, ProjectGithubRepository, ProjectLifecycleTransition,
                        ProjectStudent, SrsReviewHistory, SrsSubmission, Student)
from app.services.project_service import compute_progress

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"
DOCX = b"PK\x03\x04" + b"0" * 64


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def world(make_user, login):
    """Batch with mentor M1 (assigned), mentor M2 (not assigned), 2 students, student X (other project), lead, other lead."""
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
    su = {n: make_user("student", f"{n}@x.com") for n in ("s1", "s2", "s3")}
    db.session.flush()
    studs = {n: Student(user_id=u.id, batch_id=batch.id, registration_no=n.upper()) for n, u in su.items()}
    db.session.add_all(studs.values())
    ps = ProblemStatement(ps_code="PS1", title="Attendance", domain_id=domain("AIML").id, description="d")
    db.session.add(ps)
    db.session.flush()
    projects = {}
    for n, members in (("p1", ["s1"]), ("p2", ["s2", "s3"])):  # p1 individual, p2 team
        p = Project(batch_id=batch.id, problem_statement_id=ps.id, title=f"Project {n}", stage="srs_preparation")
        db.session.add(p)
        db.session.flush()
        for i, m in enumerate(members):
            db.session.add(ProjectStudent(project_id=p.id, student_id=studs[m].id, is_lead=(i == 0 and len(members) > 1)))
        projects[n] = p
    db.session.commit()
    H = {k: login(f"{k}@x.com") for k in ("admin", "la", "lb", "m1", "m2", "s1", "s2", "s3")}
    return dict(H=H, p1=projects["p1"], p2=projects["p2"], m1u=m1u, s1u=su["s1"], batch=batch)


def submit(client, world, who, project, name="srs.pdf", content=PDF, desc="First draft"):
    return client.post(f"/api/srs/projects/{project.id}", headers=world["H"][who], content_type="multipart/form-data",
                       data={"file": (io.BytesIO(content), name), "description": desc})


def review(client, world, who, sub_id, decision, remarks=None):
    return client.post(f"/api/srs/submissions/{sub_id}/review", headers=world["H"][who],
                       json={"decision": decision, "remarks": remarks})


def sid(resp):
    return resp.get_json()["data"]["submissions"][0]["id"]


def stage(project):
    db.session.expire_all()
    return db.session.get(Project, project.id).stage


# ------------------------------------------------------------------ submission
def test_student_submits_srs_and_stage_advances(client, world):
    r = submit(client, world, "s1", world["p1"])
    d = r.get_json()["data"]
    assert r.status_code == 201 and d["status"] == "submitted" and d["status_label"] == "Submitted"
    assert d["submissions"][0]["version"] == 1 and d["submissions"][0]["file"]["name"] == "srs.pdf"
    assert d["can_submit"] is False and d["implementation_unlocked"] is False
    assert stage(world["p1"]) == "srs_submitted"
    att = db.session.query(FileAttachment).one()
    assert att.category == "srs" and att.storage_key.startswith("srs/") and att.uploaded_by == world["s1u"].id


def test_docx_accepted_and_file_rules_enforced(client, world):
    assert submit(client, world, "s1", world["p1"], "srs.docx", DOCX).status_code == 201
    p2 = world["p2"]
    assert submit(client, world, "s2", p2, "srs.exe", b"MZ").status_code == 422
    assert submit(client, world, "s2", p2, "fake.pdf", b"not pdf").status_code == 422
    assert submit(client, world, "s2", p2, "notes.txt", b"hello").status_code == 422     # only PDF/DOCX for SRS
    assert submit(client, world, "s2", p2, "empty.pdf", b"").status_code == 422
    assert client.post(f"/api/srs/projects/{p2.id}", headers=world["H"]["s2"]).status_code == 422   # no file
    assert stage(p2) == "srs_preparation" and db.session.query(SrsSubmission).count() == 1


def test_only_project_members_can_submit(client, world):
    assert submit(client, world, "s1", world["p2"]).status_code == 404         # not their project
    assert submit(client, world, "m1", world["p1"]).status_code == 403         # mentors can't submit
    assert submit(client, world, "la", world["p1"]).status_code == 403
    assert submit(client, world, "admin", world["p1"]).status_code == 403
    # a team member (not the 'lead') may submit for the team
    assert submit(client, world, "s3", world["p2"]).status_code == 201


def test_cannot_submit_in_wrong_stage(client, world):
    p = world["p1"]
    for st in ("allocated", "srs_submitted", "srs_under_review", "srs_approved", "implementation"):
        p.stage = st
        db.session.commit()
        r = submit(client, world, "s1", p)
        assert r.status_code == 409, st
    assert db.session.query(SrsSubmission).count() == 0


def test_mentor_notified_on_submission(client, world):
    submit(client, world, "s1", world["p1"])
    n = db.session.query(Notification).filter_by(user_id=world["m1u"].id, type="srs_submitted").one()
    assert n.link == f"/srs/{world['p1'].id}"


# ---------------------------------------------------------------------- review
def test_full_approval_flow_unlocks_implementation(client, world):
    p = world["p1"]
    sub = sid(submit(client, world, "s1", p))
    r = review(client, world, "m1", sub, "start_review")
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "under_review" and stage(p) == "srs_under_review"
    assert review(client, world, "m1", sub, "start_review").status_code == 409        # already under review
    # implementation stays locked until approval
    assert client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["s1"], json={"to": "implementation"}).status_code == 409
    r = review(client, world, "m1", sub, "approve", "Looks good")
    d = r.get_json()["data"]
    assert d["status"] == "approved" and d["implementation_unlocked"] is True and stage(p) == "srs_approved"
    assert d["submissions"][0]["history"][-1]["remarks"] == "Looks good"
    t = client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["s1"], json={"to": "implementation"})
    assert t.status_code == 200 and t.get_json()["data"]["stage"] == "implementation"
    assert db.session.query(Notification).filter_by(type="srs_approved", user_id=world["s1u"].id).count() == 1


def test_approve_directly_from_submitted(client, world):
    sub = sid(submit(client, world, "s1", world["p1"]))
    assert review(client, world, "m1", sub, "approve").status_code == 200
    assert stage(world["p1"]) == "srs_approved"


@pytest.mark.parametrize("decision", ["reject", "request_changes"])
def test_remarks_required_for_reject_and_changes(client, world, decision):
    sub = sid(submit(client, world, "s1", world["p1"]))
    for remarks in (None, "", "  ", "x"):
        r = review(client, world, "m1", sub, decision, remarks)
        assert r.status_code == 422 and "Comments are required" in r.get_json()["message"]
    assert stage(world["p1"]) == "srs_submitted"
    assert review(client, world, "m1", sub, decision, "Add non-functional requirements").status_code == 200
    assert stage(world["p1"]) == "srs_changes_requested"


def test_resubmission_versions_and_history_are_preserved(client, world):
    p = world["p1"]
    v1 = sid(submit(client, world, "s1", p, desc="v1"))
    review(client, world, "m1", v1, "request_changes", "Missing use cases")
    n = db.session.query(Notification).filter_by(user_id=world["s1u"].id, type="srs_changes_requested").one()
    assert "Missing use cases" in n.message
    r = submit(client, world, "s1", p, desc="v2")                                   # allowed after changes requested
    assert r.status_code == 201
    v2 = r.get_json()["data"]["submissions"][0]
    assert v2["version"] == 2 and v2["status"] == "submitted"
    review(client, world, "m1", v2["id"], "reject", "Still incomplete")
    assert stage(p) == "srs_changes_requested"                                      # rejected → must resubmit
    v3 = submit(client, world, "s1", p, desc="v3").get_json()["data"]["submissions"][0]
    review(client, world, "m1", v3["id"], "approve", "Great")
    data = client.get(f"/api/srs/projects/{p.id}", headers=world["H"]["s1"]).get_json()["data"]
    assert [s["version"] for s in data["submissions"]] == [3, 2, 1]
    assert [s["status"] for s in data["submissions"]] == ["approved", "rejected", "changes_requested"]
    flat = [(s["version"], h["decision"], h["reviewer"]) for s in reversed(data["submissions"]) for h in s["history"]]
    assert flat == [(1, "changes_requested", "Mentor"), (2, "rejected", "Mentor"), (3, "approved", "Mentor")]
    # lifecycle audit trail has every step with timestamps
    stages = [t.to_stage for t in db.session.query(ProjectLifecycleTransition).filter_by(project_id=p.id).order_by(ProjectLifecycleTransition.id)]
    assert stages == ["srs_submitted", "srs_changes_requested", "srs_submitted", "srs_changes_requested", "srs_submitted", "srs_approved"]
    assert db.session.query(SrsReviewHistory).count() == 3


def test_only_latest_version_and_only_once(client, world):
    p = world["p1"]
    v1 = sid(submit(client, world, "s1", p))
    review(client, world, "m1", v1, "request_changes", "Fix it please")
    v2 = submit(client, world, "s1", p).get_json()["data"]["submissions"][0]["id"]
    assert review(client, world, "m1", v1, "approve").status_code == 409            # old version
    assert review(client, world, "m1", v2, "approve").status_code == 200
    assert review(client, world, "m1", v2, "reject", "Changed my mind").status_code == 409   # already decided


def test_unknown_decision_rejected(client, world):
    sub = sid(submit(client, world, "s1", world["p1"]))
    assert review(client, world, "m1", sub, "maybe").status_code == 422


def test_review_permissions(client, world):
    sub = sid(submit(client, world, "s1", world["p1"]))
    assert review(client, world, "s1", sub, "approve").status_code == 403           # student can't approve own SRS
    assert review(client, world, "la", sub, "approve").status_code == 403           # lead is read-only
    assert review(client, world, "lb", sub, "approve").status_code == 403
    assert review(client, world, "m2", sub, "approve").status_code == 404           # unassigned mentor
    assert stage(world["p1"]) == "srs_submitted"
    assert review(client, world, "admin", sub, "approve").status_code == 200        # admin may act


def test_review_writes_audit_and_activity(client, world):
    sub = sid(submit(client, world, "s1", world["p1"]))
    review(client, world, "m1", sub, "approve")
    actions = {a.action for a in db.session.query(AuditLog)}
    assert {"srs.submit", "srs.approve"} <= actions


# ------------------------------------------------------------ download & queue
def test_download_access_control(client, world, app):
    sub = sid(submit(client, world, "s1", world["p1"]))
    ok_users = ("s1", "m1", "la", "admin")
    for u in ok_users:
        r = client.get(f"/api/srs/submissions/{sub}/download", headers=world["H"][u])
        assert r.status_code == 200 and r.data == PDF, u
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        r.close()
    for u in ("s2", "m2", "lb"):
        assert client.get(f"/api/srs/submissions/{sub}/download", headers=world["H"][u]).status_code == 404, u
    assert client.get(f"/api/srs/submissions/{sub}/download").status_code == 401
    assert client.get("/api/srs/submissions/9999/download", headers=world["H"]["s1"]).status_code == 404


def test_srs_summary_scoped(client, world):
    submit(client, world, "s1", world["p1"])
    assert client.get(f"/api/srs/projects/{world['p1'].id}", headers=world["H"]["m1"]).status_code == 200
    assert client.get(f"/api/srs/projects/{world['p1'].id}", headers=world["H"]["s2"]).status_code == 404
    assert client.get(f"/api/srs/projects/{world['p1'].id}", headers=world["H"]["m2"]).status_code == 404
    fresh = client.get(f"/api/srs/projects/{world['p2'].id}", headers=world["H"]["s2"]).get_json()["data"]
    assert fresh["status"] == "not_submitted" and fresh["can_submit"] is True and fresh["submissions"] == []


def test_review_queue_scoped_and_ordered(client, world):
    submit(client, world, "s1", world["p1"])
    submit(client, world, "s2", world["p2"])
    q = lambda u: client.get("/api/srs/queue", headers=world["H"][u]).get_json()  # noqa: E731
    assert q("m1")["meta"]["total"] == 2 and q("la")["meta"]["total"] == 2 and q("admin")["meta"]["total"] == 2
    assert q("m2")["meta"]["total"] == 0 and q("lb")["meta"]["total"] == 0
    assert q("m1")["data"][0]["srs_version"] == 1
    sub = db.session.query(SrsSubmission).filter_by(project_id=world["p1"].id).one()
    review(client, world, "m1", sub.id, "approve")
    assert q("m1")["meta"]["total"] == 1                                              # decided items leave the queue
    assert client.get("/api/srs/queue", headers=world["H"]["s1"]).status_code == 403


# --------------------------------------------------------------------- GitHub
def gh(client, world, who, project, url, desc="Backend + UI"):
    return client.put(f"/api/github/projects/{project.id}", headers=world["H"][who], json={"url": url, "description": desc})


def approve(client, world, project, student="s1"):
    sub = sid(submit(client, world, student, project))
    review(client, world, "m1", sub, "approve")


@pytest.mark.parametrize("url", [
    "https://github.com/owner/repo", "https://github.com/owner/repo/", "https://github.com/owner/repo.git",
    "https://www.github.com/Owner-1/my.repo_2", "  https://github.com/owner/repo  ",
])
def test_valid_github_urls_are_normalised(client, world, url):
    approve(client, world, world["p1"])
    r = gh(client, world, "s1", world["p1"], url)
    assert r.status_code == 200
    assert r.get_json()["data"]["repository"]["url"] in ("https://github.com/owner/repo", "https://github.com/Owner-1/my.repo_2")


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo", "https://gitlab.com/owner/repo", "https://github.com/owner", "https://github.com/",
    "https://github.com/owner/repo/tree/main", "https://github.com.evil.com/owner/repo", "github.com/owner/repo",
    "javascript:alert(1)", "https://github.com/-bad/repo", "https://github.com/owner/..", "", "not a url",
    "https://github.com/owner/repo?x=1", "https://evil.com/https://github.com/owner/repo",
])
def test_invalid_github_urls_rejected(client, world, url):
    approve(client, world, world["p1"])
    r = gh(client, world, "s1", world["p1"], url)
    assert r.status_code in (422,), url
    assert db.session.query(ProjectGithubRepository).count() == 0


def test_github_locked_until_srs_approved_and_member_only(client, world):
    assert gh(client, world, "s1", world["p1"], "https://github.com/o/r").status_code == 409     # SRS not approved
    approve(client, world, world["p1"])
    assert gh(client, world, "s2", world["p1"], "https://github.com/o/r").status_code == 404     # not a member
    assert gh(client, world, "m1", world["p1"], "https://github.com/o/r").status_code == 403
    assert gh(client, world, "la", world["p1"], "https://github.com/o/r").status_code == 403
    assert gh(client, world, "s1", world["p1"], "https://github.com/o/r").status_code == 200


def test_github_update_and_visibility(client, world):
    p = world["p1"]
    approve(client, world, p)
    gh(client, world, "s1", p, "https://github.com/o/first", "v1")
    gh(client, world, "s1", p, "https://github.com/o/second", "v2")
    assert db.session.query(ProjectGithubRepository).count() == 1                   # updated in place
    for u in ("s1", "m1", "la", "admin"):
        d = client.get(f"/api/github/projects/{p.id}", headers=world["H"][u]).get_json()["data"]
        assert d["repository"]["url"] == "https://github.com/o/second" and d["repository"]["description"] == "v2", u
    for u in ("s2", "m2", "lb"):
        assert client.get(f"/api/github/projects/{p.id}", headers=world["H"][u]).status_code == 404
    detail = client.get(f"/api/projects/{p.id}", headers=world["H"]["m1"]).get_json()["data"]
    assert detail["github_url"] == "https://github.com/o/second"
    empty = client.get(f"/api/github/projects/{world['p2'].id}", headers=world["H"]["s2"]).get_json()["data"]
    assert empty["repository"] is None and empty["implementation_unlocked"] is False


def test_team_members_share_one_repository(client, world):
    p = world["p2"]
    approve(client, world, p, "s2")
    gh(client, world, "s2", p, "https://github.com/team/app")
    assert gh(client, world, "s3", p, "https://github.com/team/app2").status_code == 200
    assert client.get(f"/api/github/projects/{p.id}", headers=world["H"]["s2"]).get_json()["data"]["repository"]["url"].endswith("app2")


def test_progress_reflects_srs_and_github(client, world):
    p = world["p1"]
    assert compute_progress(p) == 0
    approve(client, world, p)
    db.session.expire_all()
    assert compute_progress(db.session.get(Project, p.id)) == 20
    gh(client, world, "s1", p, "https://github.com/o/r")
    db.session.expire_all()
    assert compute_progress(db.session.get(Project, p.id)) == 25


def test_project_detail_exposes_srs_state(client, world):
    d = client.get(f"/api/projects/{world['p1'].id}", headers=world["H"]["s1"]).get_json()["data"]
    assert d["srs_status"] == "not_submitted" and d["implementation_unlocked"] is False
    approve(client, world, world["p1"])
    d = client.get(f"/api/projects/{world['p1'].id}", headers=world["H"]["s1"]).get_json()["data"]
    assert d["srs_status"] == "approved" and d["implementation_unlocked"] is True


def test_reopening_to_srs_preparation_allows_resubmission(client, world):
    p = world["p1"]
    approve(client, world, p)
    client.post(f"/api/projects/{p.id}/transition", headers=world["H"]["s1"], json={"to": "implementation"})
    r = client.post(f"/api/projects/{p.id}/reopen", headers=world["H"]["admin"], json={"to": "srs_preparation", "reason": "SRS invalid"})
    assert r.status_code == 200
    v = submit(client, world, "s1", p, desc="revised").get_json()["data"]["submissions"][0]
    assert v["version"] == 2                                                         # versions keep counting
    assert client.get(f"/api/srs/projects/{p.id}", headers=world["H"]["s1"]).get_json()["data"]["implementation_unlocked"] is False


def test_uploaded_srs_stored_outside_public_paths(client, world, app):
    submit(client, world, "s1", world["p1"], "../../evil.pdf")
    att = db.session.query(FileAttachment).one()
    root = os.path.realpath(app.config["UPLOAD_FOLDER"])
    assert os.path.realpath(os.path.join(root, att.storage_key)).startswith(root) and ".." not in att.storage_key
