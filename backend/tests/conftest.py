import pytest

from app import create_app
from app.cli import seed_reference_data
from app.config import TestConfig
from app.extensions import db
from app.services.auth_service import create_user


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """Tests create/login hundreds of users; production scrypt would dominate the runtime.
    Hashes stay in the standard werkzeug format, so check_password_hash still verifies them."""
    from werkzeug.security import generate_password_hash as real
    monkeypatch.setattr("app.models.user.generate_password_hash", lambda pw: real(pw, method="pbkdf2:sha256:1"))


@pytest.fixture()
def app(tmp_path):
    app = create_app(TestConfig)
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")  # isolated storage per test
    with app.app_context():
        db.create_all()
        seed_reference_data()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    def _make(role="admin", email=None, password="Passw0rd!x", **kw):
        email = email or f"{role}@test.local"
        u = create_user(role, kw.pop("name", role.title()), email, password, must_change_password=False)
        db.session.commit()
        return u
    return _make


@pytest.fixture()
def login(client):
    def _login(email, password="Passw0rd!x"):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.get_json()
        return {"Authorization": f"Bearer {r.get_json()['data']['access_token']}"}
    return _login
