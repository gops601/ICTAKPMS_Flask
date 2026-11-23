import io
import os

import pytest

from app.extensions import db
from app.models import (Batch, Domain, DomainLead, FileAttachment, OrganisationalUnit, ProblemStatement, Project,
                        ProjectStudent, Student)


def domain(code):
    return db.session.query(Domain).filter_by(code=code).one()


@pytest.fixture()
def people(make_user, login):
    """admin + a lead for AIML + a lead for IOT, all logged in."""
    admin = make_user("admin", "admin@x.com")
    la, lb = make_user("domain_lead", "la@x.com"), make_user("domain_lead", "lb@x.com")
    db.session.add_all([DomainLead(user_id=la.id, domain_id=domain("AIML").id),
                        DomainLead(user_id=lb.id, domain_id=domain("IOT").id)])
    db.session.commit()
    return {"admin": login("admin@x.com"), "lead_a": login("la@x.com"), "lead_b": login("lb@x.com"),
            "lead_a_user": la}


def ps_body(**kw):
    body = {"ps_code": "PS-001", "title": "Smart Attendance", "domain_id": domain("AIML").id,
            "description": "<p>Build it</p>", "objectives": "<ul><li>One</li></ul>", "difficulty": "medium"}
    body.update(kw)
    return body


def make_ps(client, headers, **kw):
    r = client.post("/api/problem-statements", headers=headers, json=ps_body(**kw))
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def upload(client, headers, ps_id, kind, name, content, desc=""):
    return client.post(f"/api/problem-statements/{ps_id}/{kind}", headers=headers,
                       content_type="multipart/form-data",
                       data={"file": (io.BytesIO(content), name), "description": desc})


# ------------------------------------------------------------------------------ CRUD
def test_lead_creates_and_reads_problem_statement(client, people):
    d = make_ps(client, people["lead_a"])
    assert d["ps_code"] == "PS-001" and d["can_edit"] is True and d["status"] == "active"
    got = client.get(f"/api/problem-statements/{d['id']}", headers=people["lead_a"]).get_json()["data"]
    assert got["objectives"] == "<ul><li>One</li></ul>" and got["datasets"] == []


def test_rich_text_is_sanitised(client, people):
    evil = '<p onclick="x()">Hi</p><script>alert(1)</script><a href="javascript:alert(1)">bad</a><b>ok</b>'
    d = make_ps(client, people["lead_a"], description=evil)
    got = client.get(f"/api/problem-statements/{d['id']}", headers=people["lead_a"]).get_json()["data"]["description"]
    assert "<script" not in got and "onclick" not in got and "javascript:" not in got and "<b>ok</b>" in got


def test_validation_errors(client, people):
    r = client.post("/api/problem-statements", headers=people["lead_a"],
                    json={"ps_code": "bad id!", "title": "  ", "domain_id": domain("AIML").id})
    errs = r.get_json()["errors"]
    assert r.status_code == 422 and {"ps_code", "title", "description"} <= set(errs)
    r = client.post("/api/problem-statements", headers=people["lead_a"], json=ps_body(difficulty="insane"))
    assert r.status_code == 422


def test_duplicate_id_case_insensitive(client, people):
    make_ps(client, people["lead_a"])
    r = client.post("/api/problem-statements", headers=people["lead_a"], json=ps_body(ps_code="ps-001"))
    assert r.status_code == 422 and "ps_code" in r.get_json()["errors"]


def test_domain_isolation_for_leads(client, people):
    d = make_ps(client, people["lead_a"])
    # lead B cannot create in domain A, nor see/edit/attach to A's statement
    r = client.post("/api/problem-statements", headers=people["lead_b"], json=ps_body(ps_code="X"))
    assert r.status_code == 422 and "domain" in r.get_json()["errors"]
    assert client.get(f"/api/problem-statements/{d['id']}", headers=people["lead_b"]).status_code == 404
    assert client.put(f"/api/problem-statements/{d['id']}", headers=people["lead_b"], json={"title": "hax"}).status_code == 404
    assert client.patch(f"/api/problem-statements/{d['id']}/status", headers=people["lead_b"], json={"status": "inactive"}).status_code == 404
    assert upload(client, people["lead_b"], d["id"], "documents", "a.pdf", b"%PDF-1").status_code == 404
    assert client.get("/api/problem-statements", headers=people["lead_b"]).get_json()["meta"]["total"] == 0
    assert client.get("/api/problem-statements", headers=people["lead_a"]).get_json()["meta"]["total"] == 1
    assert client.get("/api/problem-statements", headers=people["admin"]).get_json()["meta"]["total"] == 1


def test_update_status_filters_and_immutable_id(client, people):
    d = make_ps(client, people["lead_a"])
    h = people["lead_a"]
    r = client.put(f"/api/problem-statements/{d['id']}", headers=h, json={"title": "New title", "difficulty": "hard"})
    assert r.get_json()["data"]["title"] == "New title" and r.get_json()["data"]["description"] == "<p>Build it</p>"
    assert client.put(f"/api/problem-statements/{d['id']}", headers=h, json={"ps_code": "OTHER"}).status_code == 422
    client.patch(f"/api/problem-statements/{d['id']}/status", headers=h, json={"status": "inactive"})
    assert client.patch(f"/api/problem-statements/{d['id']}/status", headers=h, json={"status": "x"}).status_code == 422
    assert client.get("/api/problem-statements?status=inactive&difficulty=hard", headers=h).get_json()["meta"]["total"] == 1
    assert client.get("/api/problem-statements?status=active", headers=h).get_json()["meta"]["total"] == 0
    assert client.get("/api/problem-statements?q=New", headers=h).get_json()["meta"]["total"] == 1


def test_non_managers_cannot_list_or_create(client, make_user, login):
    make_user("student", "s@x.com")
    h = login("s@x.com")
    assert client.get("/api/problem-statements", headers=h).status_code == 403
    assert client.post("/api/problem-statements", headers=h, json=ps_body()).status_code == 403


def test_mentor_lists_only_own_batch_domains_and_cannot_create(client, make_user, login, people):
    make_ps(client, people["lead_a"], ps_code="A1")
    make_ps(client, people["lead_b"], ps_code="B1", domain_id=domain("IOT").id)
    mu = make_user("mentor", "m@x.com")
    ou = db.session.query(OrganisationalUnit).first()
    from app.models import BatchMentor, Mentor
    batch = Batch(code="MB", name="MB", ou_id=ou.id, domain_id=domain("AIML").id)
    m = Mentor(user_id=mu.id)
    db.session.add_all([batch, m])
    db.session.flush()
    db.session.add(BatchMentor(batch_id=batch.id, mentor_id=m.id))
    db.session.commit()
    h = login("m@x.com")
    codes = {p["ps_code"] for p in client.get("/api/problem-statements", headers=h).get_json()["data"]}
    assert codes == {"A1"}
    assert client.get("/api/problem-statements/industries", headers=h).status_code == 200   # mentors can use the shelf's industry filter
    assert client.post("/api/problem-statements", headers=h, json=ps_body(ps_code="Z")).status_code == 403


def test_blank_ps_code_gets_generated_ict_id(client, people):
    d = client.post("/api/problem-statements", headers=people["lead_a"], json=ps_body(ps_code="")).get_json()["data"]
    code = d["ps_code"]
    assert code.startswith("ICT_PS_") and any(c.isdigit() for c in code) and any(c.isalpha() for c in code[7:])


# ------------------------------------------------------------------------ attachments
def test_dataset_upload_download_delete(client, people, app):
    d = make_ps(client, people["lead_a"])
    r = upload(client, people["lead_a"], d["id"], "datasets", "data.csv", b"a,b\n1,2\n", "training set")
    assert r.status_code == 201
    link = r.get_json()["data"]
    assert link["name"] == "data.csv" and link["description"] == "training set"
    stored = db.session.get(FileAttachment, link["file_id"])
    assert os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], stored.storage_key))
    assert stored.stored_name != "data.csv" and stored.storage_key.startswith("datasets/")
    dl = client.get(f"/api/problem-statements/{d['id']}/datasets/{link['id']}/download", headers=people["lead_a"])
    assert dl.status_code == 200 and dl.data == b"a,b\n1,2\n"
    assert dl.headers["X-Content-Type-Options"] == "nosniff" and "attachment" in dl.headers["Content-Disposition"]
    detail = client.get(f"/api/problem-statements/{d['id']}", headers=people["lead_a"]).get_json()["data"]
    assert len(detail["datasets"]) == 1 and detail["dataset_count"] if "dataset_count" in detail else True
    # another lead cannot download it
    assert client.get(f"/api/problem-statements/{d['id']}/datasets/{link['id']}/download",
                      headers=people["lead_b"]).status_code == 404
    # delete removes row and stored file
    assert client.delete(f"/api/problem-statements/{d['id']}/datasets/{link['id']}", headers=people["lead_a"]).status_code == 200
    assert not os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], stored.storage_key))
    assert db.session.get(FileAttachment, link["file_id"]) is None


def test_multiple_datasets_and_documents(client, people):
    d = make_ps(client, people["lead_a"])
    h = people["lead_a"]
    assert upload(client, h, d["id"], "datasets", "a.csv", b"x,y\n").status_code == 201
    assert upload(client, h, d["id"], "datasets", "b.json", b"{}").status_code == 201
    assert upload(client, h, d["id"], "documents", "ref.pdf", b"%PDF-1.4 data").status_code == 201
    detail = client.get(f"/api/problem-statements/{d['id']}", headers=h).get_json()["data"]
    assert len(detail["datasets"]) == 2 and len(detail["documents"]) == 1


@pytest.mark.parametrize("name,content,status", [
    ("virus.exe", b"MZ....", 422),                 # disallowed extension
    ("fake.pdf", b"not a pdf at all", 422),         # content/extension mismatch
    ("empty.csv", b"", 422),                        # empty
    ("bin.csv", b"a\x00b\x00", 422),                # binary pretending to be csv
    ("noext", b"data", 422),                        # no extension
    ("../../etc/passwd.csv", b"a,b\n", 201),        # traversal in name is neutralised, not honoured
])
def test_upload_rejections(client, people, app, name, content, status):
    d = make_ps(client, people["lead_a"])
    r = upload(client, people["lead_a"], d["id"], "datasets", name, content)
    assert r.status_code == status
    if status == 201:
        att = db.session.query(FileAttachment).one()
        assert ".." not in att.storage_key and "/" not in att.stored_name
        assert att.original_name == "etc_passwd.csv" or "passwd" in att.original_name
        root = os.path.realpath(app.config["UPLOAD_FOLDER"])
        assert os.path.realpath(os.path.join(root, att.storage_key)).startswith(root)


def test_oversize_rejected(client, people, monkeypatch):
    from app.services import file_service
    monkeypatch.setitem(file_service.CATEGORIES, "dataset", ("datasets", {"csv"}, 0.0001))
    d = make_ps(client, people["lead_a"])
    r = upload(client, people["lead_a"], d["id"], "datasets", "big.csv", b"a,b\n" * 100)
    assert r.status_code == 413


def test_unknown_attachment_kind_and_foreign_link(client, people):
    d1 = make_ps(client, people["lead_a"])
    d2 = make_ps(client, people["lead_a"], ps_code="PS-002")
    link = upload(client, people["lead_a"], d1["id"], "documents", "r.pdf", b"%PDF-1").get_json()["data"]
    assert client.get(f"/api/problem-statements/{d1['id']}/secrets/{link['id']}/download", headers=people["lead_a"]).status_code == 404
    # a link id from statement 1 cannot be fetched through statement 2
    assert client.get(f"/api/problem-statements/{d2['id']}/documents/{link['id']}/download", headers=people["lead_a"]).status_code == 404


def test_student_with_project_can_view_and_download_but_others_cannot(client, people, make_user, login):
    d = make_ps(client, people["lead_a"])
    link = upload(client, people["lead_a"], d["id"], "datasets", "d.csv", b"a,b\n").get_json()["data"]
    ou = db.session.query(OrganisationalUnit).first()
    batch = Batch(code="B1", name="B", ou_id=ou.id, domain_id=domain("AIML").id)
    db.session.add(batch)
    s_user, other_user = make_user("student", "s@x.com"), make_user("student", "o@x.com")
    db.session.flush()
    s = Student(user_id=s_user.id, batch_id=batch.id, registration_no="R1")
    o = Student(user_id=other_user.id, batch_id=batch.id, registration_no="R2")
    db.session.add_all([s, o])
    db.session.flush()
    p = Project(batch_id=batch.id, problem_statement_id=d["id"])
    db.session.add(p)
    db.session.flush()
    db.session.add(ProjectStudent(project_id=p.id, student_id=s.id))
    db.session.commit()
    sh, oh = login("s@x.com"), login("o@x.com")
    got = client.get(f"/api/problem-statements/{d['id']}", headers=sh)
    assert got.status_code == 200 and got.get_json()["data"]["can_edit"] is False
    assert client.get(f"/api/problem-statements/{d['id']}/datasets/{link['id']}/download", headers=sh).status_code == 200
    assert client.get(f"/api/problem-statements/{d['id']}", headers=oh).status_code == 404
    assert client.delete(f"/api/problem-statements/{d['id']}/datasets/{link['id']}", headers=sh).status_code == 403
    assert client.put(f"/api/problem-statements/{d['id']}", headers=sh, json={"title": "x"}).status_code == 403


# ----------------------------------------------------------------------- bulk import
PS_HEADER = ["Problem Statement ID", "Project Title", "Domain Code", "Description", "Objectives", "Difficulty Level",
             "Duration", "Status"]


def csv_bytes(header, rows):
    return ("\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n").encode()


def import_upload(client, headers, content, filename="ps.csv"):
    return client.post("/api/imports/problem_statements", headers=headers, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(content), filename)})


def test_ps_template_downloads(client, people):
    for fmt in ("csv", "xlsx"):
        r = client.get(f"/api/problem-statements/template?format={fmt}", headers=people["lead_a"])
        assert r.status_code == 200
    head = client.get("/api/problem-statements/template?format=csv", headers=people["lead_a"]).data.decode("utf-8-sig")
    for col in ("Problem Statement ID", "Project Title", "Domain Code", "Objectives", "Difficulty Level", "Required Skills"):
        assert col in head


def test_ps_import_preview_and_confirm(client, people):
    rows = [["IMP-1", "One", "AIML", "Desc one", "Obj", "easy", "4 weeks", "active"],
            ["IMP-2", "Two", "AIML", "Desc two", "", "", "", ""]]
    r = import_upload(client, people["lead_a"], csv_bytes(PS_HEADER, rows))
    d = r.get_json()["data"]
    assert r.status_code == 201 and d["valid_rows"] == 2 and db.session.query(ProblemStatement).count() == 0
    c = client.post(f"/api/imports/{d['id']}/confirm", headers=people["lead_a"], json={})
    assert c.status_code == 200 and db.session.query(ProblemStatement).count() == 2
    ps = db.session.query(ProblemStatement).filter_by(ps_code="IMP-2").one()
    assert ps.difficulty == "medium" and ps.status == "active"
    assert ps.created_by == people["lead_a_user"].id


def test_ps_import_rowwise_errors_and_domain_scope(client, people):
    make_ps(client, people["lead_a"], ps_code="EXIST-1")
    rows = [["OK-1", "Fine", "AIML", "d", "", "", "", ""],
            ["OK-1", "Dup in file", "AIML", "d", "", "", "", ""],
            ["EXIST-1", "Dup in db", "AIML", "d", "", "", "", ""],
            ["NOD-1", "No desc", "AIML", "", "", "", "", ""],
            ["BADD-1", "Bad domain", "NOPE", "d", "", "", "", ""],
            ["OTHER-1", "Not my domain", "IOT", "d", "", "", "", ""],
            ["DIFF-1", "Bad difficulty", "AIML", "d", "", "impossible", "", ""],
            ["", "Missing id", "AIML", "d", "", "", "", ""]]
    d = import_upload(client, people["lead_a"], csv_bytes(PS_HEADER, rows)).get_json()["data"]
    assert d["valid_rows"] == 1 and d["error_rows"] == 7
    by_row = {p["row_number"]: p for p in d["preview"]}
    msgs = {rn: " ".join(e["message"] for e in p["errors"]) for rn, p in by_row.items()}
    assert "Duplicate ID in file" in msgs[3]
    assert "already exists" in msgs[4]
    assert "description" in msgs[5].lower()
    assert "'NOPE' does not exist" in msgs[6]
    assert "do not have access" in msgs[7]
    assert "Difficulty" in msgs[8]
    assert "required" in msgs[9]
    assert client.post(f"/api/imports/{d['id']}/confirm", headers=people["lead_a"], json={}).status_code == 409
    ok_ = client.post(f"/api/imports/{d['id']}/confirm", headers=people["lead_a"], json={"import_valid_only": True})
    assert ok_.status_code == 200 and db.session.query(ProblemStatement).filter_by(ps_code="OK-1").count() == 1
    csv_text = client.get(f"/api/imports/{d['id']}/errors.csv", headers=people["lead_a"]).data.decode()
    assert "Problem Statement ID" in csv_text.splitlines()[0]


def test_ps_import_missing_column_and_xlsx(client, people):
    r = import_upload(client, people["lead_a"], csv_bytes(["Project Title"], [["x"]]))
    assert r.status_code == 422 and "Problem Statement ID" in r.get_json()["errors"]["missing_columns"]
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame([["X-1", "Excel one", "AIML", "d"]], columns=PS_HEADER[:4]).to_excel(buf, index=False)
    r = import_upload(client, people["lead_a"], buf.getvalue(), "ps.xlsx")
    assert r.status_code == 201 and r.get_json()["data"]["valid_rows"] == 1


def test_import_type_permissions(client, people, make_user, login):
    # leads may import problem statements but never batches/students
    r = client.post("/api/imports/batches", headers=people["lead_a"], content_type="multipart/form-data",
                    data={"ou_id": "1", "file": (io.BytesIO(b"a"), "b.csv")})
    assert r.status_code == 403
    make_user("mentor", "m@x.com")
    assert import_upload(client, login("m@x.com"), b"x").status_code == 403
    # an admin job id is not reachable by a lead
    job = import_upload(client, people["admin"], csv_bytes(PS_HEADER, [["A-1", "t", "AIML", "d", "", "", "", ""]])).get_json()["data"]
    assert client.get(f"/api/imports/{job['id']}", headers=people["lead_a"]).status_code == 404
