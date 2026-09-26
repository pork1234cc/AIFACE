"""实际 API 和 Worker 入口的授权边界与退出行为。"""

import pytest
from fastapi.testclient import TestClient
from test_licensing import FakeLicenseClient, runtime_for

from app.config import Settings
from app.main import create_app
from app.worker import run_licensed_worker


def test_api_denies_business_until_activation_and_after_revocation(tmp_path):
    fake = FakeLicenseClient()
    runtime = runtime_for(fake)
    settings = Settings(_env_file=None, AIFACE_DATABASE_PATH=tmp_path / "test.sqlite3")
    app = create_app(settings, license_runtime=runtime)
    entered = []

    @app.get("/api/test-business")
    def business():
        entered.append(True)
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/api/test-business")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "license_required"
        assert not entered
        assert client.get("/api/license/status").json()["authorized"] is False
        assert client.get("/api/health").status_code == 503  # 未迁移，不是授权拒绝。
        assert client.get("/api/docs").status_code == 403
        assert client.post("/api/license/activate", json={"code": "  "}).status_code == 422
        assert not fake.calls
        response = client.post("/api/license/activate", json={"code": "test-code"})
        assert response.status_code == 200
        assert response.json()["authorized"] is True
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/test-business").status_code == 200
        assert entered == [True]
        fake.allow = False
        assert client.post("/api/license/verify").status_code == 403
        assert client.get("/api/test-business").status_code == 403
        assert entered == [True]
        assert "sensitive-test-code" not in client.get("/api/license/status").text


def test_activation_failure_does_not_open_business(tmp_path):
    fake = FakeLicenseClient()
    fake.allow = False
    app = create_app(
        Settings(_env_file=None, AIFACE_DATABASE_PATH=tmp_path / "test.sqlite3"),
        license_runtime=runtime_for(fake),
    )
    with TestClient(app) as client:
        response = client.post("/api/license/activate", json={"code": "bad"})
        assert response.status_code == 403
        assert client.get("/api/orders").status_code == 403


def test_worker_never_constructed_without_authorization():
    class Gate:
        def authorized(self):
            return False

    def forbidden(_settings):
        raise AssertionError("未授权不应创建业务 Worker")

    assert run_licensed_worker(Gate(), None, once=True, worker_factory=forbidden) == 1


def test_worker_waits_then_runs_and_stops_steps_after_revocation():
    events = []

    class Gate:
        states = iter([False, True, False])

        def authorized(self):
            try:
                return next(self.states)
            except StopIteration:
                raise KeyboardInterrupt from None

    class FakeWorker:
        def __init__(self, _settings):
            events.append("construct")

        def __enter__(self):
            events.append("enter")

        def step(self):
            events.append("step")
            return True

        def close(self):
            events.append("close")

    with pytest.raises(KeyboardInterrupt):
        run_licensed_worker(
            Gate(), None, worker_factory=FakeWorker, sleep=lambda delay: events.append(delay)
        )
    assert events == [2, "construct", "enter", "step", 2, "close"]
