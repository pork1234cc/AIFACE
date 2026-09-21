"""交付图自动更新、切回历史、下载及终态并发约束。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_revisions import generated
from test_worker import FakeProvider, drain

from app.models.orders import Asset, GenerationTask, OrderDelivery
from app.services.deliveries import build_export, plan_export, record_export
from app.services.orders import BusinessError, write_session
from app.worker import Worker

client = api_client


def get_finals(client, order_id):
    response = client.get(f"/api/orders/{order_id}/finals")
    assert response.status_code == 200
    return response.json()


def test_auto_current_revision_failure_success_switch_and_download(client):
    order_id, base_id, _ = generated(client)
    path = f"/api/orders/{order_id}"
    assert get_finals(client, order_id)["items"][0]["asset_id"] == base_id
    first_download = client.get(path + "/delivery")
    assert first_download.status_code == 200
    assert first_download.headers["content-type"] == "image/png"
    assert "attachment" in first_download.headers["content-disposition"]
    assert first_download.content == client.get(f"/api/images/{base_id}/content").content
    assert client.get(path).json()["status"] == "review"
    result = client.post(
        path + "/revise",
        headers={"Idempotency-Key": "revision-delivery"},
        json={"config": {"base_asset_id": base_id, "extra_requirement": "去掉眼镜"}},
    ).json()
    provider = FakeProvider()
    with write_session(client.app.state.engine) as session:
        task = session.get(GenerationTask, result["tasks"][0]["id"])
        provider.results[task.provider_idempotency_key] = "failed"
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
        assert get_finals(client, order_id)["items"][0]["asset_id"] == base_id
        client.post(
            f"/api/batches/{result['batch_id']}/retry",
            headers={"Idempotency-Key": "retry-delivery"},
            json={"slot_indices": [0]},
        ).raise_for_status()
        drain(worker)
    finals = get_finals(client, order_id)
    new_id = finals["items"][0]["asset_id"]
    assert new_id != base_id and len(finals["versions"]) == 2
    assert sum(item["revoked_at"] is not None for item in finals["history"]) == 1
    assert client.put(path + "/finals", json={"asset_ids": [base_id]}).status_code == 200
    switched = get_finals(client, order_id)
    assert len(switched["history"]) == 3
    assert client.put(path + "/finals", json={"asset_ids": [base_id]}).json() == switched
    assert client.get(path + "/delivery").content == first_download.content
    assert client.post(path + "/complete").json()["status"] == "completed"
    assert client.post(path + "/complete").status_code == 200
    assert client.get(path + "/delivery").status_code == 200
    assert client.put(path + "/finals", json={"asset_ids": [new_id]}).status_code == 409
    assert client.post(path + "/close").status_code == 409


def test_current_cannot_be_discarded_and_cross_order_rejected(client):
    order_id, base_id, inputs = generated(client)
    other_id, foreign_id, _ = generated(client)
    path = f"/api/orders/{order_id}/finals"
    for ids in [
        [base_id, foreign_id],
        [foreign_id],
        [inputs.config.base_asset_id],
        [base_id, base_id],
    ]:
        assert client.put(path, json={"asset_ids": ids}).status_code == 422
    review_path = f"/api/images/{base_id}/review"
    assert client.patch(review_path, json={"review_status": "discarded"}).status_code == 409
    assert client.put(path, json={"asset_ids": []}).status_code == 200
    assert client.patch(review_path, json={"review_status": "discarded"}).status_code == 200
    assert client.put(path, json={"asset_ids": [base_id]}).status_code == 422
    assert get_finals(client, other_id)["items"][0]["asset_id"] == foreign_id


@pytest.mark.parametrize("open_status", ["pending", "running", "needs_attention"])
def test_no_completion_or_close_while_generation_open(client, open_status):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        from app.models.orders import GenerationBatch

        session.get(GenerationBatch, batch.id).status = open_status
    for action in ["complete", "close"]:
        assert client.post(f"/api/orders/{order_id}/{action}").status_code == 409
    assert client.put(f"/api/orders/{order_id}/finals", json={"asset_ids": []}).status_code == 409


def test_empty_order_can_close_but_not_complete(client):
    order_id, _ = ready(client)
    path = f"/api/orders/{order_id}"
    assert client.get(path + "/delivery").status_code == 409
    assert client.post(path + "/complete").status_code == 409
    assert client.post(path + "/close").json()["status"] == "closed"
    assert client.post(path + "/close").status_code == 200
    assert client.post(path + "/complete").status_code == 409


def test_export_rechecks_selection_and_missing_file_does_not_mark_export(client):
    order_id, base_id, _ = generated(client)
    with write_session(client.app.state.engine) as session:
        plan = plan_export(session, order_id)
    file = build_export(client.app.state.settings.storage_path, plan)
    assert file.content
    client.put(f"/api/orders/{order_id}/finals", json={"asset_ids": []}).raise_for_status()
    with write_session(client.app.state.engine) as session:
        with pytest.raises(BusinessError, match="已变化"):
            record_export(session, plan)
    client.put(f"/api/orders/{order_id}/finals", json={"asset_ids": [base_id]}).raise_for_status()
    with write_session(client.app.state.engine) as session:
        session.get(Asset, base_id).relative_path = f"orders/{order_id}/missing.png"
    assert client.get(f"/api/orders/{order_id}/delivery").status_code == 404
    assert client.post(f"/api/orders/{order_id}/complete").status_code == 404
    assert get_finals(client, order_id)["items"][0]["last_exported_at"] is None


def test_concurrent_current_selection_and_complete_vs_generate(client):
    order_id, base_id, payload = generated(client)
    path = f"/api/orders/{order_id}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.put(path + "/finals", json={"asset_ids": [base_id]}), range(2)
            )
        )
    assert all(response.status_code == 200 for response in responses)
    with write_session(client.app.state.engine) as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(OrderDelivery).where(
                            OrderDelivery.order_id == order_id, OrderDelivery.revoked_at.is_(None)
                        )
                    )
                )
            )
            == 1
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        finish = pool.submit(client.post, path + "/complete")
        generate = pool.submit(
            client.post,
            path + "/generate",
            json=payload.model_dump(),
            headers={"Idempotency-Key": "concurrent-delivery"},
        )
    assert sorted([finish.result().status_code, generate.result().status_code]) in [
        [200, 409],
        [202, 409],
    ]
