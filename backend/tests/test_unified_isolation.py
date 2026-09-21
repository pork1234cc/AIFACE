"""新旧任务隔离与预览/提交一致性。"""

import pytest
from sqlalchemy import text
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_orders_api import create, upload
from test_worker import FakeProvider

from app.models.orders import Asset, GenerationBatch, GenerationTask
from app.schemas.orders import Params
from app.services.orders import write_session
from app.worker import Worker

client = api_client


def test_worker_never_claims_legacy_pending_task(client):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        # 在隔离测试库构造旧协议任务；应用代码不执行任何旧格式映射。
        session.execute(text(
            "INSERT INTO orders SELECT id,order_no,customer_name,note,source_channel,"
            "style_id,'ready',params_json,created_at,updated_at FROM v2_orders"
        ))
        session.execute(
            text(
                "INSERT INTO assets SELECT id,order_id,kind,'person_main',"
                "is_active_input,generation_task_id,relative_path,original_name,"
                "mime_type,byte_size,width,height,sha256,review_status,sort_index,"
                "created_at FROM v2_assets"
            )
        )
        session.execute(text("INSERT INTO generation_batches SELECT * FROM v2_generation_batches"))
        session.execute(text("INSERT INTO generation_tasks SELECT * FROM v2_generation_tasks"))
        session.get(GenerationBatch, batch.id).status = "failed"
        for task in session.query(GenerationTask).all():
            task.status = "failed"
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        assert worker.step() is False
    assert provider.submits == []
    with write_session(client.app.state.engine) as session:
        assert session.scalar(text("SELECT status FROM generation_tasks")) == "pending"
        assert session.scalar(text("SELECT count(*) FROM orders")) == 1
    assert client.get(f"/api/orders/{order_id}").status_code == 200


def test_preview_and_submit_reject_same_missing_file(client):
    order_id, payload = ready(client)
    with write_session(client.app.state.engine) as session:
        session.get(
            Asset, payload.config.base_asset_id
        ).relative_path = f"orders/{order_id}/missing.png"
    responses = [
        client.post(
            f"/api/orders/{order_id}/{endpoint}",
            json=payload.model_dump(),
            headers={"Idempotency-Key": "missing-input"},
        )
        for endpoint in ["prompt-preview", "generate"]
    ]
    assert responses[0].status_code == responses[1].status_code == 404
    assert responses[0].json()["error"]["code"] == responses[1].json()["error"]["code"]


def test_four_distinct_sources_rejected_before_model(client):
    order_id = create(client)
    base = upload(client, order_id, "main").json()
    sources = [upload(client, order_id).json()["id"] for _ in range(3)] + ["missing-fourth"]
    config = Params(
        base_asset_id=base["id"],
        changes=[
            dict(
                target_description=f"对象{index}",
                change_type="服装",
                instruction="替换",
                source_asset_ids=[source],
            )
            for index, source in enumerate(sources)
        ],
    )
    response = client.post(
        f"/api/orders/{order_id}/prompt-preview", json={"config": config.model_dump()}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "order_not_ready"


@pytest.mark.parametrize(
    "ratio", ["16:9", "21:9", "4:3", "3:2", "5:4", "1:1", "4:5", "2:3", "3:4", "9:16", "9:21"]
)
def test_documented_ratios_pass_through(ratio):
    assert Params(aspect_ratio=ratio).aspect_ratio == ratio
