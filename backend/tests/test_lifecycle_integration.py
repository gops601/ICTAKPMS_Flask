import io

from tests.lifecycle_flow import run


def test_complete_project_lifecycle(client, make_user):
    """Spec §18: OU → domain → batch → lead → problem → mentor → allocation → SRS → GitHub → Scrum → 4 reviews → completion."""
    make_user("admin", "admin@flow.test", password="Admin#Pass1")

    def call(method, path, token=None, json=None, files=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        kwargs = {"headers": headers}
        if files:
            kwargs.update(content_type="multipart/form-data", data={k: (io.BytesIO(v[1]), v[0]) for k, v in files.items()})
        elif json is not None:
            kwargs["json"] = json
        resp = getattr(client, method.lower())(path, **kwargs)
        return resp.status_code, resp.get_json()

    result = run(call, "admin@flow.test", "Admin#Pass1", tag="t1")
    assert result["stages"][-1] == "completed" and result["notifications"] >= 5
