"""修改的单图约束、来源/版本/幂等与人工选择边界。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_orders_api import upload
from test_worker import FakeProvider, drain

from app.models.orders import Asset, GenerationBatch
from app.schemas.generation import RetryRequest, ReviewRequest, RevisionRequest
from app.services.generation import latest_tasks, retry_batch
from app.services.orders import BusinessError, get_order, write_session
from app.services.revisions import create_revision, review_result, revision_stats
from app.worker import Worker

client = api_client


def test_revision_and_review_api_contract(client):
    order_id, base_id, _ = generated(client)
    path = f"/api/orders/{order_id}"
    assert client.post(path + "/request-revision").json()["status"] == "revision_requested"
    response = client.post(
        path + "/revise",
        headers={"Idempotency-Key": "api-revision"},
        json={"base_asset_id": base_id, "instruction": "去掉眼镜"},
    )
    assert response.status_code == 202
    batch = response.json()
    assert batch["target_count"] == 1 and batch["operation"] == "revision"
    assert batch["base_asset_id"] == base_id and batch["style_version"]
    assert batch["inputs"] == [{"asset_id": base_id, "role": "base"}]
    assert client.get(path + "/generation-stats").json()["revision_count"] == 1
    assert (
        client.patch(f"/api/images/{base_id}/review", json={"review_status": "selected"}).json()[
            "review_status"
        ]
        == "selected"
    )
    assert (
        client.patch(f"/api/images/{base_id}/review", json={"review_status": "other"}).status_code
        == 422
    )
    assert (
        client.post(
            path + "/revise", json={"base_asset_id": base_id, "instruction": "修改"}
        ).status_code
        == 422
    )


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


def test_revision_concurrent_replay_style_lineage_and_single_output(client):
    order_id, base_id, _ = generated(client)
    payload = RevisionRequest(base_asset_id=base_id, instruction=" 去掉眼镜 ")
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: revise(client, order_id, payload), range(2)))
    batch = batches[0]
    assert batch.id == batches[1].id
    assert batch.target_count == 1 and batch.base_asset_id == base_id
    assert batch.revision_instruction == "去掉眼镜"
    assert "保留原有眼镜" not in batch.prompt_snapshot
    assert batch.params_snapshot_json["glasses_keep"] is True
    assert len(batch.input_snapshot_json) == 1
    with write_session(client.app.state.engine) as session:
        initial = session.scalar(
            select(GenerationBatch).where(
                GenerationBatch.order_id == order_id, GenerationBatch.operation == "initial"
            )
        )
        assert batch.style_snapshot_json == initial.style_snapshot_json
        assert list(latest_tasks(session, batch.id)) == [0]
        assert revision_stats(session, order_id)["revision_count"] == 1
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert len(provider.submits) == 1
    with write_session(client.app.state.engine) as session:
        assert revision_stats(session, order_id)["successful_revision_count"] == 1
        output = session.scalar(
            select(Asset).where(
                Asset.generation_task_id.in_(
                    [t.id for t in latest_tasks(session, batch.id).values()]
                )
            )
        )
        next_base = output.id
    second = revise(
        client,
        order_id,
        RevisionRequest(base_asset_id=next_base, instruction="头发蓬松一点"),
        "second-revision",
    )
    assert second.style_snapshot_json == batch.style_snapshot_json
    with write_session(client.app.state.engine) as session:
        get_order(session, order_id).status = "closed"
    assert revise(client, order_id, payload).id == batch.id
    with pytest.raises(BusinessError, match="同一请求"):
        revise(client, order_id, payload.model_copy(update={"instruction": "另一要求"}))


def test_four_input_limit_sources_and_empty_instruction(client):
    order_id, base_id, inputs = generated(client)
    aux = upload(client, order_id).json()
    ref = upload(client, order_id, "reference").json()
    fourth = upload(client, order_id).json()
    extra = inputs.model_dump()["inputs"] + [
        {"asset_id": a["id"], "role": a["input_role"]} for a in (aux, ref)
    ]
    for instruction in ["", "  ", "\n\t"]:
        with pytest.raises(ValidationError):
            RevisionRequest(base_asset_id=base_id, instruction=instruction)
    with pytest.raises(ValidationError):
        RevisionRequest(
            base_asset_id=base_id,
            instruction="改",
            additional_inputs=extra + [{"asset_id": fourth["id"], "role": "person_aux"}],
        )
    for selected in [
        extra[:1] * 2,
        [{"asset_id": base_id, "role": "person_main"}],
        [{"asset_id": aux["id"], "role": "reference"}],
    ]:
        with pytest.raises(BusinessError):
            revise(
                client,
                order_id,
                RevisionRequest(
                    base_asset_id=base_id, instruction="去掉眼镜", additional_inputs=selected
                ),
            )
    other, foreign, _ = generated(client)
    with pytest.raises(BusinessError):
        revise(client, order_id, RevisionRequest(base_asset_id=foreign, instruction="修改"))
    batch = revise(
        client,
        order_id,
        RevisionRequest(base_asset_id=base_id, instruction="去掉眼镜", additional_inputs=extra),
    )
    assert len(batch.input_snapshot_json) == 4
    assert batch.input_snapshot_json[0]["asset_id"] == base_id
    assert other != order_id


def test_retry_preserves_round_and_review_is_reversible(client):
    order_id, base_id, inputs = generated(client)
    client.put(f"/api/orders/{order_id}/finals", json={"asset_ids": []}).raise_for_status()
    with write_session(client.app.state.engine) as session:
        for status in ("selected", "discarded", "unreviewed"):
            assert (
                review_result(session, base_id, ReviewRequest(review_status=status)).review_status
                == status
            )
        with pytest.raises(BusinessError):
            review_result(
                session, inputs.inputs[0].asset_id, ReviewRequest(review_status="selected")
            )
        review_result(session, base_id, ReviewRequest(review_status="discarded"))
    payload = RevisionRequest(base_asset_id=base_id, instruction="去掉眼镜")
    with pytest.raises(BusinessError, match="作废"):
        revise(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        review_result(session, base_id, ReviewRequest(review_status="unreviewed"))
    batch = revise(client, order_id, payload)
    provider = FakeProvider()
    with write_session(client.app.state.engine) as session:
        task = latest_tasks(session, batch.id)[0]
        provider.results[task.provider_idempotency_key] = "failed"
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
        with write_session(client.app.state.engine) as session:
            retry_batch(session, batch.id, RetryRequest(slot_indices=[0]), "retry-revision")
            assert revision_stats(session, order_id)["revision_count"] == 1
        drain(worker)
    assert len(provider.submits) == 2
    with write_session(client.app.state.engine) as session:
        stats = revision_stats(session, order_id)
        assert stats == {
            "revision_count": 1,
            "successful_revision_count": 1,
            "generation_attempt_count": 3,
            "submitted_attempt_count": 3,
        }
        assert len(latest_tasks(session, batch.id)) == 1
        get_order(session, order_id).status = "completed"
    with write_session(client.app.state.engine) as session:
        with pytest.raises(BusinessError, match="只读"):
            review_result(session, base_id, ReviewRequest(review_status="discarded"))


def test_missing_base_file_and_inactive_additional_input(client):
    order_id, base_id, inputs = generated(client)
    with write_session(client.app.state.engine) as session:
        session.get(Asset, inputs.inputs[0].asset_id).is_active_input = False
    with pytest.raises(BusinessError):
        revise(
            client,
            order_id,
            RevisionRequest(
                base_asset_id=base_id, instruction="修改", additional_inputs=inputs.inputs
            ),
        )
    with write_session(client.app.state.engine) as session:
        session.get(Asset, base_id).relative_path = f"orders/{order_id}/missing.png"
    with pytest.raises(BusinessError):
        revise(client, order_id, RevisionRequest(base_asset_id=base_id, instruction="修改"))
    with write_session(client.app.state.engine) as session:
        assert revision_stats(session, order_id)["revision_count"] == 0
