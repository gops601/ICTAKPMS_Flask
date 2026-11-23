from app.extensions import db
from app.models import User


def test_login_success_and_me(client, make_user, login):
    make_user("admin", "a@x.com")
    h = login("a@x.com")
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200
    assert r.get_json()["data"]["role"] == "admin"


def test_login_wrong_password_generic_message(client, make_user):
    make_user("admin", "a@x.com")
    r = client.post("/api/auth/login", json={"email": "a@x.com", "password": "nope"})
    assert r.status_code == 401
    r2 = client.post("/api/auth/login", json={"email": "ghost@x.com", "password": "nope"})
    assert r.get_json()["message"] == r2.get_json()["message"]


def test_login_validation_error_envelope(client):
    r = client.post("/api/auth/login", json={"email": "bad"})
    assert r.status_code == 422
    assert r.get_json()["success"] is False


def test_lockout_after_repeated_failures(client, make_user, app):
    make_user("admin", "a@x.com")
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        client.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong"})
    r = client.post("/api/auth/login", json={"email": "a@x.com", "password": "Passw0rd!x"})
    assert r.status_code == 423


def test_inactive_user_cannot_login(client, make_user):
    u = make_user("student", "s@x.com")
    u.is_active = False
    db.session.commit()
    r = client.post("/api/auth/login", json={"email": "s@x.com", "password": "Passw0rd!x"})
    assert r.status_code == 403


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_user_token_rejected(client, make_user, login):
    u = make_user("mentor", "m@x.com")
    h = login("m@x.com")
    u.is_active = False
    db.session.commit()
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_change_password(client, make_user, login):
    make_user("student", "s@x.com")
    h = login("s@x.com")
    bad = client.post("/api/auth/change-password", headers=h,
                      json={"current_password": "wrong", "new_password": "NewPass123"})
    assert bad.status_code == 400
    weak = client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "Passw0rd!x", "new_password": "short"})
    assert weak.status_code == 422
    good = client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "Passw0rd!x", "new_password": "NewPass123"})
    assert good.status_code == 200
    assert client.post("/api/auth/login", json={"email": "s@x.com", "password": "NewPass123"}).status_code == 200


def test_forgot_and_reset_password(client, make_user):
    make_user("student", "s@x.com")
    r = client.post("/api/auth/forgot-password", json={"email": "s@x.com"})
    token = r.get_json()["data"]["token"]
    unknown = client.post("/api/auth/forgot-password", json={"email": "none@x.com"})
    assert unknown.status_code == 200 and unknown.get_json()["data"] is None
    ok = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Brand1New99"})
    assert ok.status_code == 200
    reuse = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Another1Pass"})
    assert reuse.status_code == 400
    assert client.post("/api/auth/login", json={"email": "s@x.com", "password": "Brand1New99"}).status_code == 200


def test_refresh_token(client, make_user):
    make_user("admin", "a@x.com")
    r = client.post("/api/auth/login", json={"email": "a@x.com", "password": "Passw0rd!x"})
    refresh = r.get_json()["data"]["refresh_token"]
    r2 = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {refresh}"})
    assert r2.status_code == 200 and "access_token" in r2.get_json()["data"]


def test_passwords_are_hashed(make_user):
    u = make_user("admin", "a@x.com")
    assert u.password_hash != "Passw0rd!x" and db.session.get(User, u.id).check_password("Passw0rd!x")
