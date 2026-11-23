import io

import pandas as pd
import pytest

from app.extensions import db
from app.models import Batch, Domain, ImportJob, OrganisationalUnit, Student, User


@pytest.fixture()
def admin(make_user, login):
    make_user("admin", "admin@x.com")
    return login("admin@x.com")


def ou(code):
    return db.session.query(OrganisationalUnit).filter_by(code=code).one()


def upload(client, headers, kind, ou_id, content, filename="data.csv"):
    return client.post(f"/api/imports/{kind}", headers=headers, content_type="multipart/form-data",
                       data={"ou_id": str(ou_id), "file": (io.BytesIO(content), filename)})


def csv_bytes(header, rows):
    return ("\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n").encode()


ACADEMIC_HEADER = ["Batch Code", "Batch Name", "Domain Code", "Start Date", "End Date", "University", "College",
                   "Programme", "Academic Year", "Semester"]


def good_row(code="AC-1"):
    return [code, "Batch " + code, "AIML", "2026-01-05", "2026-02-05", "KU", "CET", "BTech", "2026", "7"]


def xlsx_bytes(header, rows):
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=header).to_excel(buf, index=False)
    return buf.getvalue()


# -------------------------------------------------------------------- templates
@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
@pytest.mark.parametrize("code", ["RETAIL", "ACADEMIC", "CORPORATE", "GOVERNMENT"])
def test_batch_templates_are_ou_specific(client, admin, code, fmt):
    r = client.get(f"/api/ous/{ou(code).id}/template?type=batches&format={fmt}", headers=admin)
    assert r.status_code == 200
    if fmt == "csv":
        header = r.data.decode("utf-8-sig").splitlines()[0]
    else:
        header = ",".join(pd.read_excel(io.BytesIO(r.data)).columns)
    assert "Batch Code" in header
    expected = {"RETAIL": "Programme Name", "ACADEMIC": "University", "CORPORATE": "Company Name",
                "GOVERNMENT": "Nodal Officer"}[code]
    assert expected in header


def test_template_reflects_runtime_field_changes(client, admin):
    oid = ou("RETAIL").id
    client.post(f"/api/ous/{oid}/fields", headers=admin, json={"label": "Region"})
    r = client.get(f"/api/ous/{oid}/template?type=batches&format=csv", headers=admin)
    assert "Region" in r.data.decode("utf-8-sig")


def test_student_template_includes_core_columns(client, admin):
    r = client.get(f"/api/ous/{ou('ACADEMIC').id}/template?type=students&format=csv", headers=admin)
    header = r.data.decode("utf-8-sig")
    for col in ("Student Name", "Email", "Phone Number", "Registration Number", "Batch Code"):
        assert col in header


# ---------------------------------------------------------------------- batch import
def test_batch_import_preview_then_confirm(client, admin):
    content = csv_bytes(ACADEMIC_HEADER, [good_row("AC-1"), good_row("AC-2")])
    r = upload(client, admin, "batches", ou("ACADEMIC").id, content)
    data = r.get_json()["data"]
    assert r.status_code == 201 and data["valid_rows"] == 2 and data["error_rows"] == 0
    assert db.session.query(Batch).count() == 0  # nothing written before confirmation
    c = client.post(f"/api/imports/{data['id']}/confirm", headers=admin, json={})
    assert c.status_code == 200 and c.get_json()["data"]["imported_rows"] == 2
    assert db.session.query(Batch).count() == 2
    b = db.session.query(Batch).filter_by(code="AC-1").one()
    assert {d.field.field_key: d.value for d in b.ou_details}["college"] == "CET"
    # a confirmed job cannot be confirmed twice
    assert client.post(f"/api/imports/{data['id']}/confirm", headers=admin, json={}).status_code == 409


def test_batch_import_rowwise_errors_block_confirm(client, admin):
    rows = [good_row("AC-1"),
            good_row("AC-1"),  # duplicate in file
            ["", "No code", "AIML", "2026-01-05", "2026-02-05", "KU", "CET", "BTech", "", ""],
            ["AC-3", "Bad domain", "NOPE", "2026-01-05", "2026-02-05", "KU", "CET", "BTech", "", ""],
            ["AC-4", "Bad date", "AIML", "garbage", "", "KU", "CET", "BTech", "", ""],
            ["AC-5", "Missing req", "AIML", "", "", "", "", "", "", ""]]
    r = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, rows))
    d = r.get_json()["data"]
    assert d["valid_rows"] == 1 and d["error_rows"] == 5
    by_row = {p["row_number"]: p for p in d["preview"]}
    assert by_row[2]["status"] == "valid"
    assert "Duplicate" in by_row[3]["errors"][0]["message"]
    assert any("Domain code 'NOPE'" in e["message"] for e in by_row[5]["errors"])
    assert any(e["field"] == "start_date" for e in by_row[6]["errors"])
    assert {e["field"] for e in by_row[7]["errors"]} >= {"details.university", "details.college", "details.programme"}
    # refuses silently-partial import
    assert client.post(f"/api/imports/{d['id']}/confirm", headers=admin, json={}).status_code == 409
    assert db.session.query(Batch).count() == 0
    # explicit valid-only import works
    ok_ = client.post(f"/api/imports/{d['id']}/confirm", headers=admin, json={"import_valid_only": True})
    assert ok_.status_code == 200 and db.session.query(Batch).count() == 1


def test_batch_import_detects_existing_codes(client, admin):
    upload_one = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, [good_row("AC-1")]))
    client.post(f"/api/imports/{upload_one.get_json()['data']['id']}/confirm", headers=admin, json={})
    r = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, [good_row("ac-1")]))
    d = r.get_json()["data"]
    assert d["error_rows"] == 1 and "already exists" in d["preview"][0]["errors"][0]["message"]


def test_import_accepts_xlsx_with_excel_dates(client, admin):
    df_rows = [good_row("AC-9")]
    content = xlsx_bytes(ACADEMIC_HEADER, df_rows)
    r = upload(client, admin, "batches", ou("ACADEMIC").id, content, "batches.xlsx")
    assert r.status_code == 201 and r.get_json()["data"]["valid_rows"] == 1


def test_import_rejects_bad_files(client, admin):
    oid = ou("ACADEMIC").id
    assert upload(client, admin, "batches", oid, b"x", "data.txt").status_code == 422
    assert upload(client, admin, "batches", oid, b"", "data.csv").status_code == 422
    r = upload(client, admin, "batches", oid, csv_bytes(["Batch Code"], [["A"]]))
    assert r.status_code == 422 and "Batch Name" in r.get_json()["errors"]["missing_columns"]
    assert upload(client, admin, "batches", oid, csv_bytes(ACADEMIC_HEADER, [])).status_code == 422
    assert upload(client, admin, "unknown", oid, b"x").status_code == 404


def test_import_is_admin_only_and_job_private(client, admin, make_user, login):
    make_user("domain_lead", "l@x.com")
    h = login("l@x.com")
    assert upload(client, h, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, [good_row()])).status_code == 403
    r = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, [good_row()]))
    assert r.status_code == 201, r.get_json()
    jid = r.get_json()["data"]["id"]
    make_user("admin", "admin2@x.com")
    other = login("admin2@x.com")
    assert client.get(f"/api/imports/{jid}", headers=other).status_code == 404
    assert client.post(f"/api/imports/{jid}/confirm", headers=other, json={}).status_code == 404


def test_errors_csv_download_and_formula_injection_guard(client, admin):
    rows = [["=cmd|' /C calc'!A0", "Name", "NOPE", "", "", "KU", "CET", "BTech", "", ""]]
    r = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, rows))
    jid = r.get_json()["data"]["id"]
    c = client.get(f"/api/imports/{jid}/errors.csv", headers=admin)
    text = c.data.decode()
    assert c.status_code == 200 and text.startswith("row_number,field,error,Batch Code,Batch Name,Domain Code")
    assert "'=cmd" in text  # neutralised


# -------------------------------------------------------------------- student import
STUDENT_HEADER = ["Student Name", "Email", "Phone Number", "Registration Number", "Batch Code"]


@pytest.fixture()
def academic_batch(client, admin):
    r = upload(client, admin, "batches", ou("ACADEMIC").id, csv_bytes(ACADEMIC_HEADER, [good_row("AC-1")]))
    client.post(f"/api/imports/{r.get_json()['data']['id']}/confirm", headers=admin, json={})
    return db.session.query(Batch).filter_by(code="AC-1").one()


def test_student_import_creates_users_with_credentials(client, admin, academic_batch):
    rows = [["Asha K", "asha@x.com", "9999999999", "REG1", "AC-1"], ["Ben J", "ben@x.com", "", "REG2", "ac-1"]]
    r = upload(client, admin, "students", ou("ACADEMIC").id, csv_bytes(STUDENT_HEADER, rows))
    d = r.get_json()["data"]
    assert d["valid_rows"] == 2
    c = client.post(f"/api/imports/{d['id']}/confirm", headers=admin, json={}).get_json()["data"]
    assert len(c["credentials"]) == 2
    assert db.session.query(Student).filter_by(batch_id=academic_batch.id).count() == 2
    # imported students can log in with the issued temp password and must change it
    cred = next(x for x in c["credentials"] if x["email"] == "asha@x.com")
    login_r = client.post("/api/auth/login", json={"email": "asha@x.com", "password": cred["temporary_password"]})
    assert login_r.get_json()["data"]["user"]["must_change_password"] is True
    assert db.session.get(ImportJob, d["id"]).payload is None
    # re-fetching the job never exposes passwords
    assert "temporary_password" not in client.get(f"/api/imports/{d['id']}", headers=admin).get_data(as_text=True)


def test_student_import_validation(client, admin, academic_batch, make_user):
    make_user("mentor", "taken@x.com")
    rows = [["Good One", "good@x.com", "", "R1", "AC-1"],
            ["Dup Email", "good@x.com", "", "R2", "AC-1"],
            ["Taken", "taken@x.com", "", "R3", "AC-1"],
            ["Bad Email", "not-an-email", "", "R4", "AC-1"],
            ["No Batch", "nb@x.com", "", "R5", "ZZZ"],
            ["Dup Reg", "dr@x.com", "", "R1", "AC-1"],
            ["", "nn@x.com", "", "R6", "AC-1"]]
    d = upload(client, admin, "students", ou("ACADEMIC").id, csv_bytes(STUDENT_HEADER, rows)).get_json()["data"]
    assert d["valid_rows"] == 1 and d["error_rows"] == 6
    errs = client.get(f"/api/imports/{d['id']}", headers=admin).get_json()["data"]["errors"]
    fields = {(e["row_number"], e["field"]) for e in errs}
    assert {(3, "Email"), (4, "Email"), (5, "Email"), (6, "Batch Code"), (7, "Registration Number"), (8, "Student Name")} <= fields


def test_student_import_rejects_batch_from_other_ou(client, admin, academic_batch):
    rows = [["Cross OU", "c@x.com", "", "R1", "AC-1"]]
    d = upload(client, admin, "students", ou("RETAIL").id, csv_bytes(STUDENT_HEADER, rows)).get_json()["data"]
    assert d["valid_rows"] == 0 and "not found in Retail OU" in d["preview"][0]["errors"][0]["message"]
    assert client.post(f"/api/imports/{d['id']}/confirm", headers=admin, json={}).status_code == 409


def test_student_import_uses_ou_specific_student_fields(client, admin, academic_batch):
    oid = ou("ACADEMIC").id
    client.post(f"/api/ous/{oid}/fields", headers=admin,
                json={"label": "Roll Number", "scope": "student", "is_required": True})
    # header now required
    r = upload(client, admin, "students", oid, csv_bytes(STUDENT_HEADER, [["A B", "ab@x.com", "", "R1", "AC-1"]]))
    assert r.status_code == 422
    r = upload(client, admin, "students", oid,
               csv_bytes(STUDENT_HEADER + ["Roll Number"], [["A B", "ab@x.com", "", "R1", "AC-1", "77"]]))
    d = r.get_json()["data"]
    client.post(f"/api/imports/{d['id']}/confirm", headers=admin, json={})
    assert db.session.query(Student).one().extra_fields == {"roll_number": "77"}
    assert db.session.query(User).filter_by(email="ab@x.com").one().is_active
