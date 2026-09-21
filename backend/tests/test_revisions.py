"""新流程的版本血缘、多素材输入、重试与快照校验。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_orders_api import upload
from test_worker import FakeProvider, drain

from app.models.orders import Asset, GenerationBatch
from app.schemas.generation import RetryRequest, RevisionRequest
from app.services.generation import latest_tasks, retry_batch
from app.services.orders import BusinessError, write_session
from app.services.revisions import create_revision, revision_stats
from app.worker import Worker

client = api_client


def generated(client):
    order_id, inputs = ready(client)
    submit(client, order_id, inputs)
    with Worker(client.app.state.settings, FakeProvider(), 0) as worker:
        drain(worker)
    assets = client.get(f"/api/orders/{order_id}").json()["assets"]
    return order_id, next(a["id"] for a in assets if a["kind"] == "generated"), inputs


def revise(client, order_id, payload, key="revision-test"):
    with write_session(client.app.state.engine) as session:
        return create_revision(
            session, client.app.state.settings.storage_path, order_id, payload, key
        )


def request(base, **changes):
    return RevisionRequest(config={"base_asset_id": base, "style_id": None, **changes})


def test_revision_concurrent_replay_and_snapshot(client):
    order_id, base_id, _ = generated(client)
    payload = request(base_id, extra_requirement="去掉眼镜", aspect_ratio="3:4")
    path = f"/api/orders/{order_id}"
    preview = client.post(path + "/prompt-preview", json=payload.model_dump()).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: revise(client, order_id, payload), range(2)))
    batch = batches[0]
    assert batch.id == batches[1].id
    assert batch.prompt_snapshot == preview["prompt"]
    assert batch.params_snapshot_json == preview["params"]
    assert batch.style_snapshot_json["style_id"] is None
    with write_session(client.app.state.engine) as session:
        assert latest_tasks(session, batch.id)[0].request_snapshot_json["aspect_ratio"] == "3:4"
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert len(provider.submits) == 1
    current = client.get(path + "/finals").json()["items"][0]["asset_id"]
    assert current != base_id
    with pytest.raises(BusinessError, match="当前交付"):
        revise(client, order_id, request(base_id), "outdated-base")
    second = revise(client, order_id, request(current), "next-version")
    assert second.params_snapshot_json["changes"] == []
    assert "去掉眼镜" not in second.prompt_snapshot
    assert revise(client, order_id, payload).id == batch.id
    with pytest.raises(BusinessError, match="同一请求"):
        revise(client, order_id, request(base_id, extra_requirement="另一要求"))


def test_entering_revision_does_not_mark_order_as_running(client):
    order_id, _, _ = generated(client)
    response = client.post(f"/api/orders/{order_id}/request-revision")
    assert response.status_code == 200
    assert response.json()["status"] == "review"
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "review"


def test_multiple_inputs_dedup_foreign_and_missing(client):
    order_id, base_id, _ = generated(client)
    materials = [upload(client, order_id).json() for _ in range(5)]
    _, foreign, _ = generated(client)
    with pytest.raises(BusinessError):
        revise(client, order_id, request(foreign))
    changes = [
        dict(
            target_description=f"目标{i}",
            change_type="替换",
            instruction="按素材修改",
            source_asset_ids=[asset["id"]],
        )
        for i, asset in enumerate(materials)
    ]
    changes.append(dict(changes[0], target_description="另一目标"))
    batch = revise(client, order_id, request(base_id, changes=changes))
    assert len(batch.input_snapshot_json) == 6
    assert len(batch.params_snapshot_json["changes"]) == 6


def test_failed_revision_retry_keeps_round_and_previous_delivery(client):
    order_id, base_id, _ = generated(client)
    batch = revise(client, order_id, request(base_id, extra_requirement="调整发型"))
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "modifying"
    provider = FakeProvider()
    with write_session(client.app.state.engine) as session:
        provider.results[latest_tasks(session, batch.id)[0].provider_idempotency_key] = "failed"
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
        assert client.get(f"/api/orders/{order_id}").json()["status"] == "review"
        assert (
            client.get(f"/api/orders/{order_id}/finals").json()["items"][0]["asset_id"] == base_id
        )
        with write_session(client.app.state.engine) as session:
            retry_batch(session, batch.id, RetryRequest(slot_indices=[0]), "retry-revision")
            assert revision_stats(session, order_id)["revision_count"] == 1
        assert client.get(f"/api/orders/{order_id}").json()["status"] == "modifying"
        drain(worker)
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "review"
    assert len(provider.submits) == 2
    with write_session(client.app.state.engine) as session:
        assert revision_stats(session, order_id)["successful_revision_count"] == 1


def test_missing_base_and_inactive_material_create_no_task(client):
    order_id, base_id, _ = generated(client)
    asset = upload(client, order_id).json()
    client.patch(f"/api/orders/{order_id}/images/{asset['id']}/active", json={"active": False})
    payload = request(
        base_id,
        changes=[
            dict(
                target_description="脸部",
                change_type="身份",
                instruction="替换",
                source_asset_ids=[asset["id"]],
            )
        ],
    )
    with pytest.raises(BusinessError):
        revise(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        session.get(Asset, base_id).relative_path = f"orders/{order_id}/missing.png"
    with pytest.raises(BusinessError):
        revise(client, order_id, request(base_id))
    with write_session(client.app.state.engine) as session:
        assert revision_stats(session, order_id)["revision_count"] == 0
        assert len(list(session.scalars(select(GenerationBatch)))) == 1
