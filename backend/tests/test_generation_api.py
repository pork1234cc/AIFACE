"""生成与人工恢复的 HTTP 契约及幂等重放。"""

import pytest
from sqlalchemy import select
from test_generation_service import ready
from test_orders_api import client as api_client
from test_worker import FakeProvider, drain

from app.models.orders import GenerationTask
from app.services.orders import write_session
from app.worker import Worker

client = api_client


def generate(client):
    order_id, payload = ready(client)
    result = client.post(
        f"/api/orders/{order_id}/generate",
        json=payload.model_dump(),
        headers={"Idempotency-Key": "initial-key"},
    )
    assert result.status_code == 202
    return order_id, result.json()


def test_api_one_result_and_no_secrets(client):
    order_id, batch = generate(client)
    with Worker(client.app.state.settings, FakeProvider(), 0) as worker:
        drain(worker)
    response = client.get(f"/api/batches/{batch['batch_id']}")
    assert response.json()["status"] == "succeeded"
    assert len(response.json()["outputs"]) == 1
    assert "https://example.com" not in response.text
    assert "snapshot" not in response.text and "relative_path" not in response.text
    listing = client.get(f"/api/orders/{order_id}/batches").json()
    assert listing["total"] == 1
    assert client.get(f"/api/orders/{order_id}/batches?page_size=101").status_code == 422
    for task in batch["tasks"]:
        assert client.get(f"/api/tasks/{task['id']}").json()["cost_amount"] is None


@pytest.mark.parametrize("action", ["confirm_not_accepted", "resubmit_with_risk"])
def test_reconcile_idempotent_and_explicit_risk(client, action):
    _, batch = generate(client)
    provider = FakeProvider()
    provider.unknown = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    task_id = batch["tasks"][0]["id"]
    path = f"/api/tasks/{task_id}/reconcile"
    payload = {"action": action, "note": "已在供应商后台人工核对该请求"}
    headers = {"Idempotency-Key": "reconcile-key"}
    if action == "resubmit_with_risk":
        assert client.post(path, json=payload, headers=headers).status_code == 422
        payload["acknowledge_possible_duplicate_charge"] = True
    first = client.post(path, json=payload, headers=headers)
    assert first.status_code == 202
    assert client.post(path, json=payload, headers=headers).json() == first.json()
    assert (
        client.post(
            path, json=payload | {"note": "另一个不同核对说明"}, headers=headers
        ).status_code
        == 409
    )
    tasks = first.json()["tasks"]
    previous = next(t for t in tasks if t["id"] == task_id)
    assert previous["status"] == (
        "failed" if action == "confirm_not_accepted" else "superseded_unknown"
    )
    assert previous["cost_amount"] is None


def test_retry_preserves_attempts_and_blocks_success(client):
    _, batch = generate(client)
    path = f"/api/batches/{batch['batch_id']}/retry"
    headers = {"Idempotency-Key": "retry-key"}
    payload = {"slot_indices": [0]}
    assert client.post(path, json=payload, headers=headers).status_code == 409
    with write_session(client.app.state.engine) as session:
        task = session.scalar(
            select(GenerationTask).where(
                GenerationTask.batch_id == batch["batch_id"], GenerationTask.slot_index == 0
            )
        )
        task.status, task.failure_stage = "failed", "remote"
    result = client.post(path, json=payload, headers=headers)
    assert result.status_code == 202
    assert len(result.json()["tasks"]) == 2
    assert client.post(path, json=payload, headers=headers).json() == result.json()
    assert client.post(path, json={"slot_indices": [True]}, headers=headers).status_code == 422


@pytest.mark.parametrize("model", ["gpt-image-2.0-4k", "gpt-image-2", "gpt-image-2.5-sunburst"])
def test_link_remote_checks_model_and_id(client, monkeypatch, model):
    monkeypatch.setenv("image_model", model)
    _, batch = generate(client)
    provider = FakeProvider()
    provider.unknown = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    monkeypatch.setattr("app.api.generation.ApiiProvider", lambda _: provider)
    path = f"/api/tasks/{batch['tasks'][0]['id']}/reconcile"
    payload = {
        "action": "link_remote_task",
        "note": "后台核对与本次请求一致",
        "provider_task_id": "remote-id",
    }
    headers = {"Idempotency-Key": "link-remote"}
    assert client.post(path, json=payload, headers=headers).status_code == 422
    monkeypatch.setattr(
        provider,
        "query",
        lambda remote_id: {
            "task_id": remote_id,
            "status": "queued",
            "model": model,
            "type": "edit",
        },
    )
    assert client.post(path, json=payload, headers=headers).status_code == 202
    assert client.post(path, json=payload, headers=headers).status_code == 202
