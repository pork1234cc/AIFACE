"""验证健康检查、错误协议和敏感信息隔离。"""

from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("image_api", raising=False)
    return Settings(_env_file=None)


def test_health_requires_migration(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_not_ready"
    assert str(settings.database_path) not in response.text


def test_health_works_without_model_key_and_after_restart(settings):
    command.upgrade(Config(str(PROJECT_ROOT / "backend/alembic.ini")), "head")
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            response = client.get("/api/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "database": "ready", "version": "0.1.0"}
            assert UUID(response.headers["X-Request-ID"])


def test_errors_and_openapi_do_not_expose_secrets(settings, caplog):
    secret = "test-sensitive-key-never-expose"
    app = create_app(settings.model_copy(update={"image_api": secret}))

    @app.get("/test/fail")
    def fail():
        raise RuntimeError(secret)

    @app.get("/test/validate")
    def validate(count: int):
        return {"count": count}

    with TestClient(app) as client:
        for path, status in [
            ("/api/missing", 404),
            ("/test/fail", 500),
            (f"/test/validate?count={secret}", 422),
        ]:
            response = client.get(path)
            assert response.status_code == status
            assert secret not in response.text
            assert response.json()["request_id"] == response.headers["X-Request-ID"]
        assert secret not in client.get("/api/openapi.json").text
    assert secret not in caplog.text
