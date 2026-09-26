"""Sunburst 协议与订单闭环回归，使用模拟传输，不调用真实模型。"""

import base64
import io
import json

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from test_assets import image_bytes
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_orders_api import create
from test_worker import drain, state

from app.config import Settings
from app.models.orders import GenerationTask
from app.providers.apii import ApiiProvider, ProviderError, parse_result
from app.schemas.generation import RetryRequest, RevisionRequest
from app.schemas.orders import InitialInputs, Params
from app.services.generation import request_hash, retry_batch
from app.services.orders import BusinessError, write_session
from app.services.revisions import create_revision
from app.worker import Worker

client = api_client


def mask_bytes(size=(100, 100)):
    output = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 0, 0)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("ratio", ["7:5", "3:1", "1:3", "21:9"])
def test_custom_ratio(ratio):
    assert Params(aspect_ratio=ratio).aspect_ratio == ratio


@pytest.mark.parametrize("ratio", ["0:1", "4:1", "1:4", "1.5:1", "-1:2", "1:0"])
def test_invalid_ratio(ratio):
    with pytest.raises(ValidationError):
        Params(aspect_ratio=ratio)


def test_size_without_ratio():
    assert Params(aspect_ratio="", size="1024x1024").size == "1024x1024"
    with pytest.raises(ValidationError):
        Params(aspect_ratio="", size="1001x1001")


@pytest.mark.parametrize("sync", [True, False])
@pytest.mark.parametrize("mode", ["generate", "edit"])
def test_provider_routes_and_results(sync, mode):
    seen = []
    encoded = base64.b64encode(image_bytes()).decode("ascii")

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=(
                {"data": [{"b64_json": encoded}]}
                if sync
                else {"task_id": "remote-1", "status": "queued"}
            ),
        )

    provider = ApiiProvider(Settings(_env_file=None, image_api="test"), httpx.MockTransport(handle))
    try:
        result = provider.submit(
            {"_mode": mode, "async": not sync, "model": "gpt-image-2.5-sunburst"},
            [] if mode == "generate" else [image_bytes()],
            "stable",
        )
        body = json.loads(seen[0].content)
        assert seen[0].url.path == (
            "/v1/images/generations" if mode == "generate" else "/v1/images/edits"
        )
        assert "_mode" not in body
        assert ("images" in body) == (mode == "edit")
        assert result.get("b64_json") == encoded if sync else result["task_id"] == "remote-1"
    finally:
        provider.close()


def test_async_base64_result():
    encoded = base64.b64encode(image_bytes()).decode("ascii")
    result = parse_result(
        {"task_id": "remote", "status": "succeeded", "result": {"data": [{"b64_json": encoded}]}}
    )
    assert result["b64_json"] == encoded


@pytest.mark.parametrize("sync", [True, False])
def test_text_generation_base64_restart(client, sync):
    order_id = create(client)
    payload = InitialInputs(
        config={
            "mode": "generate",
            "extra_requirement": "中文测试：海边日落",
            "response_format": "b64_json",
            "async_mode": not sync,
        }
    )
    preview = client.post(f"/api/orders/{order_id}/prompt-preview", json=payload.model_dump())
    assert preview.status_code == 200, preview.text
    assert preview.json()["inputs"] == []
    assert "编辑底图" not in preview.json()["prompt"]
    batch = submit(client, order_id, payload)
    seen = []
    encoded = base64.b64encode(image_bytes()).decode("ascii")

    def handle(request):
        seen.append(request.method)
        if request.method == "POST":
            assert request.url.path == "/v1/images/generations"
            return httpx.Response(
                200,
                json={"data": [{"b64_json": encoded}]}
                if sync
                else {"task_id": "remote", "status": "queued"},
            )
        return httpx.Response(
            200,
            json={
                "task_id": "remote",
                "status": "succeeded",
                "result": {"data": [{"b64_json": encoded}]},
            },
        )

    def provider():
        return ApiiProvider(Settings(_env_file=None, image_api="test"), httpx.MockTransport(handle))

    with Worker(client.app.state.settings, provider(), 0) as worker:
        worker.step()
        if not sync:
            worker.step()
    with Worker(client.app.state.settings, provider(), 0) as worker:
        drain(worker)
    assert seen.count("POST") == 1
    assert state(client, batch.id)[0] == "succeeded"
    with write_session(client.app.state.engine) as session:
        task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
        assert "b64_json" not in task.result_metadata_json


def test_mask_size_and_binding_checked_before_submission(client):
    order_id, payload = ready(client)
    payload.config.mask = base64.b64encode(mask_bytes((7, 9))).decode("ascii")
    payload.config.mask_base_asset_id = payload.config.base_asset_id
    with pytest.raises(BusinessError, match="尺寸"):
        submit(client, order_id, payload)
    payload.config.mask_base_asset_id = "wrong-base"
    with pytest.raises(BusinessError, match="遮罩"):
        submit(client, order_id, payload)


def test_mask_not_sent_as_reference_image():
    source = image_bytes()
    with Image.open(io.BytesIO(source)) as picture:
        mask = base64.b64encode(mask_bytes(picture.size)).decode("ascii")
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"task_id": "remote", "status": "queued"})

    provider = ApiiProvider(Settings(_env_file=None, image_api="test"), httpx.MockTransport(handle))
    try:
        provider.submit({"async": True, "mask": mask}, [source], "key")
        assert seen[0]["mask"] == mask
        assert len(seen[0]["images"]) == 1
        with pytest.raises(ProviderError):
            provider.submit(
                {"async": True, "mask": base64.b64encode(mask_bytes((1, 1))).decode("ascii")},
                [source],
                "bad",
            )
        assert len(seen) == 1
    finally:
        provider.close()


MODELS = ["gpt-image-2.0-4k", "gpt-image-2", "gpt-image-2.5-sunburst"]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("mode", ["edit", "generate"])
@pytest.mark.parametrize("response_format", ["url", "b64_json"])
@pytest.mark.parametrize("async_mode", [True, False])
def test_three_model_request_matrix(model, mode, response_format, async_mode):
    encoded = base64.b64encode(image_bytes()).decode("ascii")
    item = {
        response_format: "https://example.com/image.png" if response_format == "url" else encoded
    }

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == model
        assert body["async"] is async_mode
        assert body["response_format"] == response_format
        assert request.url.path.endswith("generations" if mode == "generate" else "edits")
        return httpx.Response(
            200, json={"task_id": "task", "status": "queued"} if async_mode else {"data": [item]}
        )

    provider = ApiiProvider(Settings(_env_file=None, image_api="test"), httpx.MockTransport(handle))
    try:
        result = provider.submit(
            {
                "model": model,
                "_mode": mode,
                "async": async_mode,
                "response_format": response_format,
            },
            [] if mode == "generate" else [image_bytes()],
            "matrix",
        )
        assert result["status"] == ("queued" if async_mode else "succeeded")
    finally:
        provider.close()


def test_switch_models_preserves_existing_and_retry_snapshots(client, monkeypatch):
    batches = []
    for model in MODELS:
        monkeypatch.setenv("image_model", model)
        order_id, payload = ready(client)
        batches.append(submit(client, order_id, payload))
    with write_session(client.app.state.engine) as session:
        for batch, model in zip(batches, MODELS, strict=True):
            task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
            assert task.model == task.request_snapshot_json["model"] == model
            task.status, task.failure_stage = "failed", "remote"
            original = dict(task.request_snapshot_json)
            retry_batch(session, batch.id, RetryRequest(slot_indices=[0]), f"retry-{model}")
            newest = session.scalar(
                select(GenerationTask)
                .where(GenerationTask.batch_id == batch.id)
                .order_by(GenerationTask.attempt_no.desc())
            )
            assert newest.request_snapshot_json == original


def test_sunburst_size_limit_does_not_block_other_models(client, monkeypatch):
    order_id = create(client)
    payload = {
        "config": {
            "mode": "generate",
            "aspect_ratio": "",
            "size": "3840x2160",
            "extra_requirement": "中文输出：日落",
        }
    }
    for model in MODELS:
        monkeypatch.setenv("image_model", model)
        result = client.post(f"/api/orders/{order_id}/prompt-preview", json=payload)
        assert result.status_code == (422 if model.endswith("sunburst") else 200)


def test_sync_persist_failure_recovers_without_regeneration(client, monkeypatch):
    order_id = create(client)
    batch = submit(
        client,
        order_id,
        InitialInputs(
            config={"mode": "generate", "extra_requirement": "山水", "async_mode": False}
        ),
    )
    calls = []

    def handle(request):
        calls.append(request.method)
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(image_bytes()).decode("ascii")}]}
        )

    provider = ApiiProvider(Settings(_env_file=None, image_api="test"), httpx.MockTransport(handle))
    with Worker(client.app.state.settings, provider, 0) as worker:
        worker.step()
        original = worker._download

        def fail(task):
            raise OSError("模拟磁盘不可写")

        monkeypatch.setattr(worker, "_download", fail)
        worker.step()
        assert state(client, batch.id)[0] == "failed"
        with write_session(client.app.state.engine) as session:
            retry_batch(session, batch.id, RetryRequest(slot_indices=[0]), "resume-sync")
        monkeypatch.setattr(worker, "_download", original)
        drain(worker)
        assert state(client, batch.id)[0] == "succeeded"
    assert calls == ["POST"]
    detail = client.get(f"/api/orders/{order_id}").json()
    result_id = next(asset["id"] for asset in detail["assets"] if asset["kind"] == "generated")
    with write_session(client.app.state.engine) as session:
        revision = create_revision(
            session,
            client.app.state.settings.storage_path,
            order_id,
            RevisionRequest(
                config={"mode": "edit", "base_asset_id": result_id, "extra_requirement": "增加云朵"}
            ),
            "revise-text",
        )
        assert revision.base_asset_id == result_id


@pytest.mark.parametrize(
    "value", ["not-base64", "data:text/plain;base64,YQ==", "http://example.com/mask.png"]
)
def test_invalid_masks_are_rejected_without_submit(client, value):
    order_id, payload = ready(client)
    payload.config.mask, payload.config.mask_base_asset_id = value, payload.config.base_asset_id
    with pytest.raises(BusinessError):
        submit(client, order_id, payload)


def test_text_generation_reconcile_checks_generation_type(client, monkeypatch):
    from test_worker import FakeProvider

    order_id = create(client)
    batch = submit(
        client, order_id, InitialInputs(config={"mode": "generate", "extra_requirement": "山水"})
    )
    with write_session(client.app.state.engine) as session:
        task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
        task.status = "submission_unknown"
        task_id, model = task.id, task.model
    provider = FakeProvider()
    remote = {"task_id": "text-task", "model": model, "status": "queued", "type": "edit"}
    monkeypatch.setattr(provider, "query", lambda _: remote)
    monkeypatch.setattr("app.api.generation.ApiiProvider", lambda _: provider)
    path = f"/api/tasks/{task_id}/reconcile"
    body = {"action": "link_remote_task", "note": "已核对文生图", "provider_task_id": "text-task"}
    headers = {"Idempotency-Key": "link-text-task"}
    assert client.post(path, json=body, headers=headers).status_code == 422
    remote["type"] = "generation"
    assert client.post(path, json=body, headers=headers).status_code == 202


def test_legacy_pending_request_replay_survives_new_default_fields(client):
    from app.models.orders import GenerationBatch

    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    new_fields = {"mode", "size", "response_format", "async_mode", "mask", "mask_base_asset_id"}
    old_config = {
        key: value for key, value in payload.config.model_dump().items() if key not in new_fields
    }
    with write_session(client.app.state.engine) as session:
        saved = session.get(GenerationBatch, batch.id)
        saved.params_snapshot_json = old_config
        saved.request_hash = request_hash({"config": old_config})
    assert submit(client, order_id, payload).id == batch.id
    payload.config.response_format = "b64_json"
    with pytest.raises(BusinessError, match="同一请求"):
        submit(client, order_id, payload)
