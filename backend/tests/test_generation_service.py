"""事务预检、不可变快照及幂等边界。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_orders_api import client as api_client
from test_orders_api import create, upload

from app.models.orders import Asset, GenerationBatch, GenerationTask
from app.schemas.orders import InitialInputs
from app.services.generation import create_initial
from app.services.orders import BusinessError, get_order, write_session

client = api_client


def ready(client):
    order_id = create(client)
    asset = upload(client, order_id, "main").json()
    client.patch(f"/api/orders/{order_id}/params", json={"base_asset_id": asset["id"]})
    return order_id, InitialInputs(config={"base_asset_id": asset["id"]})


def submit(client, order_id, payload, key="test-key"):
    with write_session(client.app.state.engine) as session:
        return create_initial(
            session, client.app.state.settings.storage_path, order_id, payload, key
        )


def test_idempotent_snapshot_and_concurrent_submit(client):
    order_id, payload = ready(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(client, order_id, payload), range(2)))
    assert results[0].id == results[1].id
    with write_session(client.app.state.engine) as session:
        order = get_order(session, order_id)
        order.params_json = order.params_json | {"extra_requirement": "后来修改"}
        order.status = "closed"
    assert submit(client, order_id, payload).id == results[0].id
    assert results[0].params_snapshot_json["extra_requirement"] == ""
    with pytest.raises(BusinessError, match="同一请求"):
        submit(
            client,
            order_id,
            InitialInputs(
                config=payload.config.model_copy(update={"extra_requirement": "不同要求"})
            ),
        )


def test_missing_file_does_not_create_batch(client):
    order_id, payload = ready(client)
    with write_session(client.app.state.engine) as session:
        asset = session.get(Asset, payload.config.base_asset_id)
        asset.relative_path = f"orders/{order_id}/missing.png"
    with pytest.raises(BusinessError):
        submit(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        assert list(session.scalars(select(GenerationBatch))) == []


def test_only_one_open_batch(client):
    order_id, payload = ready(client)
    submit(client, order_id, payload)
    with pytest.raises(BusinessError, match="未结束"):
        submit(client, order_id, payload, "another-key")


@pytest.mark.parametrize("output_format", ["png", "jpeg", "webp"])
def test_output_format_is_snapshotted_for_provider(client, output_format):
    order_id, payload = ready(client)
    payload.config.output_format = output_format
    batch = submit(client, order_id, payload, f"format-{output_format}")
    with write_session(client.app.state.engine) as session:
        saved_batch = session.scalar(select(GenerationBatch).where(GenerationBatch.id == batch.id))
        task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
        assert saved_batch.params_snapshot_json["output_format"] == output_format
        assert task.request_snapshot_json["output_format"] == output_format
        assert task.request_snapshot_json["quality"] == "high"
