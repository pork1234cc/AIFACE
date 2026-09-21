"""模型设置保留原有环境项、密钥不回传，并即时影响当前 Apii 协议。"""

import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_generation_service import ready, submit
from test_orders_api import client as api_client

from app.config import Settings
from app.main import create_app
from app.models.orders import GenerationTask
from app.providers.apii import ApiiProvider
from app.services.orders import write_session

client = api_client


def test_model_settings_api_persists_without_returning_key(tmp_path, monkeypatch):
    for name in ("image_api", "image_api_url", "image_model", "image_quality"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# 原有注释\nAIFACE_STORAGE_PATH=storage/unified\nimage_api=old-secret\n", encoding="utf-8"
    )
    app = create_app(Settings(_env_file=None, AIFACE_DATABASE_PATH=tmp_path / "test.db"))
    with TestClient(app) as client:
        app.state.settings_file = path
        initial = client.get("/api/model-settings")
        assert initial.status_code == 200
        assert initial.json()["has_api_key"] is True
        assert "old-secret" not in initial.text
        payload = {
            "api_url": "https://example.test",
            "model": "new-image-model",
            "quality": "medium",
            "api_key": "new-secret",
        }
        response = client.put("/api/model-settings", json=payload)
        assert response.status_code == 200
        assert response.json() == {
            "api_url": "https://example.test",
            "model": "new-image-model",
            "quality": "medium",
            "has_api_key": True,
        }
        assert "new-secret" not in response.text
        assert "# 原有注释" in path.read_text(encoding="utf-8")
        assert "AIFACE_STORAGE_PATH=storage/unified" in path.read_text(encoding="utf-8")
        assert Settings(_env_file=path).require_image_api() == "new-secret"
        assert client.put("/api/model-settings", json=payload | {"api_key": ""}).status_code == 200
        assert Settings(_env_file=path).require_image_api() == "new-secret"
        assert (
            client.put(
                "/api/model-settings", json=payload | {"api_url": "http://localhost"}
            ).status_code
            == 422
        )
        assert (
            client.put("/api/model-settings", json=payload | {"quality": "ultra"}).status_code
            == 422
        )


def test_provider_uses_configured_url_and_omits_internal_snapshot_field():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(202, json={"task_id": "remote-1", "status": "queued"})

    settings = Settings(_env_file=None, image_api="secret", image_api_url="https://example.test")
    provider = ApiiProvider(settings, httpx.MockTransport(handle))
    try:
        provider.submit({"model": "m", "_api_url": "https://old.example.test"}, [], "key")
        assert str(seen[0].url) == "https://old.example.test/v1/images/edits"
        assert "_api_url" not in json.loads(seen[0].content)
    finally:
        provider.close()


def test_new_generation_snapshots_model_url_and_quality(client, monkeypatch):
    monkeypatch.setenv("image_model", "other-image-model")
    monkeypatch.setenv("image_api_url", "https://new.example.test")
    monkeypatch.setenv("image_quality", "low")
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload, "model-settings-snapshot")
    with write_session(client.app.state.engine) as session:
        task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
        assert task.model == "other-image-model"
        assert task.request_snapshot_json["model"] == "other-image-model"
        assert task.request_snapshot_json["_api_url"] == "https://new.example.test"
        assert task.request_snapshot_json["quality"] == "low"
