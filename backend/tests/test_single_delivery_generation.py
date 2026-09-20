"""新业务流程：首次只生成一张交付图，不创建双候选任务。"""

from test_generation_service import ready
from test_orders_api import client as api_client
from test_worker import FakeProvider, drain

from app.worker import Worker

client = api_client


def test_first_generation_creates_only_one_task_and_one_output(client):
    order_id, payload = ready(client)
    response = client.post(
        f"/api/orders/{order_id}/generate",
        json=payload.model_dump(),
        headers={"Idempotency-Key": "single-delivery-result"},
    )
    assert response.status_code == 202
    batch = response.json()
    assert batch["target_count"] == 1
    assert len(batch["tasks"]) == 1
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    result = client.get(f"/api/batches/{batch['batch_id']}").json()
    assert result["status"] == "succeeded"
    assert len(result["outputs"]) == 1
    assert len(provider.submits) == 1


def test_style_and_prompt_preview_agree_on_single_result(client):
    order_id, payload = ready(client)
    preview = client.post(f"/api/orders/{order_id}/prompt-preview", json=payload.model_dump())
    assert preview.status_code == 200
    assert preview.json()["target_count"] == 1
    style = client.get("/api/styles/q_crayon_001").json()
    assert style["initial_count"] == 1
