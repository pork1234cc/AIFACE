"""示意图队列、封面保留、恢复、版本和幂等边界。"""

import pytest
from sqlalchemy import func, select
from test_custom_styles import new_style
from test_orders_api import client as api_client
from test_worker import FakeProvider, drain

from app.config import PROJECT_ROOT
from app.models.orders import CustomStyle, Order, StylePreviewTask
from app.services import style_previews
from app.services.orders import write_session
from app.worker import Worker

client = api_client


def test_browser_mock_provider_handles_preview_tasks(client):
    import runpy

    provider_type = runpy.run_path(str(PROJECT_ROOT / "scripts/browser-qa.py"))["LocalProvider"]
    style = new_style(client)
    generate(client, style)
    client.app.state.settings.storage_path.mkdir(parents=True, exist_ok=True)
    with Worker(client.app.state.settings, provider_type(client.app.state.settings), 0) as worker:
        drain(worker)
    assert read(client, style)["cover_image"]


def generate(client, style, key="style-preview-001"):
    return client.post(
        f"/api/styles/{style['style_id']}/previews",
        json={"expected_version": int(style["version"])},
        headers={"Idempotency-Key": key},
    )


def read(client, style):
    return client.get(f"/api/styles/{style['style_id']}").json()


def test_preview_success_idempotency_and_no_orders(client):
    style = new_style(client)
    response = generate(client, style)
    assert response.status_code == 202
    first = response.json()["preview"]
    assert generate(client, style).json()["preview"] == first
    assert generate(client, style, "another-request").status_code == 409
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    result = read(client, style)
    assert result["preview"]["status"] == "succeeded"
    assert result["cover_image"]
    assert result["cover_stale"] is False
    assert client.get(result["cover_image"]).status_code == 200
    assert len(provider.submits) == 1
    assert generate(client, style).json()["preview"]["task_id"] == first["task_id"]
    with write_session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(StylePreviewTask)) == 1
        assert session.get(StylePreviewTask, first["task_id"]).download_url is None


def test_version_snapshot_and_failed_regeneration_keeps_cover(client):
    style = new_style(client)
    first = generate(client, style).json()
    updated = client.put(
        f"/api/styles/{style['style_id']}",
        json={
            "style_name": "油画",
            "prompt": "厚涂油画",
            "expected_version": 1,
        },
    ).json()
    assert generate(client, updated).status_code == 409
    with Worker(client.app.state.settings, FakeProvider(), 0) as worker:
        drain(worker)
    old = read(client, style)
    assert old["cover_stale"] is True
    with write_session(client.app.state.engine) as session:
        task = session.get(StylePreviewTask, first["preview"]["task_id"])
        assert "水彩" in task.request_snapshot_json["prompt"]
        assert "厚涂油画" not in task.request_snapshot_json["prompt"]
    failed = generate(client, updated, "regenerate-new-key").json()
    provider = FakeProvider()
    provider.results[f"preview-{failed['preview']['task_id']}"] = "failed"
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert read(client, style)["cover_image"] == old["cover_image"]
    assert read(client, style)["preview"]["status"] == "failed"
    assert generate(client, updated, "retry-new-key").status_code == 202


def test_download_resume_never_resubmits(client):
    style = new_style(client)
    task = generate(client, style).json()["preview"]
    provider = FakeProvider()
    provider.download_error = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert read(client, style)["preview"]["can_resume_download"] is True
    assert generate(client, style, "cannot-recharge").status_code == 409
    path = f"/api/styles/{style['style_id']}/previews/{task['task_id']}/resume"
    assert client.post(path).status_code == 202
    assert client.post(path).status_code == 202
    provider.download_error = False
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert len(provider.submits) == 1
    assert read(client, style)["cover_image"]


def test_uncertain_submission_blocks_retry_and_requires_explicit_reconcile(client):
    style = new_style(client)
    task = generate(client, style).json()["preview"]
    provider = FakeProvider()
    provider.unknown = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert read(client, style)["preview"]["status"] == "submission_unknown"
    assert generate(client, style, "must-not-resend").status_code == 409
    path = f"/api/styles/{style['style_id']}/previews/{task['task_id']}/reconcile"
    body = {"action": "confirm_not_accepted", "note": "已查看供应商记录"}
    assert client.post(path, json=body).status_code == 422
    body["confirmed_not_accepted"] = True
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).status_code == 200
    assert generate(client, style, "confirmed-retry").status_code == 202


def test_restart_recovers_submitting_without_duplicate(client):
    style = new_style(client)
    task = generate(client, style).json()["preview"]
    with write_session(client.app.state.engine) as session:
        session.get(StylePreviewTask, task["task_id"]).status = "submitting"
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        assert worker.step() is False
    assert read(client, style)["preview"]["status"] == "submission_unknown"
    assert not provider.submits


def test_builtin_unknown_and_cross_style_access_rejected(client):
    assert generate(client, {"style_id": "q_crayon_001", "version": "1"}).status_code == 403
    assert generate(client, {"style_id": "custom_" + "0" * 32, "version": "1"}).status_code == 404
    style, other = new_style(client), new_style(client)
    task = generate(client, style).json()["preview"]
    prefix = f"/api/styles/{other['style_id']}/previews/{task['task_id']}"
    assert client.get(prefix + "/content").status_code == 404
    assert client.post(prefix + "/resume").status_code == 404
    with write_session(client.app.state.engine) as session:
        assert session.get(CustomStyle, other["style_id"]).preview_task_id is None


def test_changed_reference_fails_before_paid_submission(client, tmp_path, monkeypatch):
    style = new_style(client)
    reference = tmp_path / "reference.png"
    reference.write_bytes(style_previews.REFERENCE_IMAGE.read_bytes())
    monkeypatch.setattr(style_previews, "REFERENCE_IMAGE", reference)
    generate(client, style)
    reference.write_bytes(b"changed")
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert read(client, style)["preview"]["status"] == "failed"
    assert not provider.submits


def test_query_failure_keeps_original_remote_task(client):
    style = new_style(client)
    generate(client, style)
    provider = FakeProvider()
    provider.query_error = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        worker.step()
        worker.step()
        assert read(client, style)["preview"]["status"] == "queued"
        provider.query_error = False
        drain(worker)
    assert read(client, style)["cover_image"]
    assert len(provider.submits) == 1


@pytest.mark.parametrize("model", ["gpt-image-2.0-4k", "gpt-image-2", "gpt-image-2.5-sunburst"])
def test_link_unknown_remote_task_and_resume_without_submission(client, monkeypatch, model):
    monkeypatch.setenv("image_model", model)
    from app.api import style_previews as api

    style = new_style(client)
    task = generate(client, style).json()["preview"]
    with write_session(client.app.state.engine) as session:
        session.get(StylePreviewTask, task["task_id"]).status = "submission_unknown"

    class VerifiedProvider(FakeProvider):
        def __init__(self, settings):
            super().__init__()

        def query(self, remote_id):
            return super().query(remote_id) | {"model": model, "type": "edit"}

    monkeypatch.setattr(api, "ApiiProvider", VerifiedProvider)
    path = f"/api/styles/{style['style_id']}/previews/{task['task_id']}/reconcile"
    body = {
        "action": "link_remote_task",
        "provider_task_id": "known-task",
        "note": "已在供应商后台核对",
    }
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).status_code == 200
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert read(client, style)["cover_image"]
    assert not provider.submits
