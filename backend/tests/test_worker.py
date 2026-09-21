"""单图流程、旧双图部分失败恢复以及崩溃后的提交不明。"""

import pytest
from sqlalchemy import select
from test_assets import image_bytes
from test_generation_service import ready, submit
from test_orders_api import client as api_client

from app.models.orders import GenerationBatch, GenerationTask
from app.providers.apii import ProviderError
from app.schemas.generation import RetryRequest
from app.services.generation import make_task, retry_batch
from app.services.orders import write_session
from app.worker import Worker

client = api_client


class FakeProvider:
    def __init__(self):
        self.submits = []
        self.results = {}
        self.query_error = False
        self.download_error = False
        self.unknown = False

    def close(self):
        pass

    def submit(self, snapshot, images, key):
        self.submits.append(key)
        if self.unknown:
            raise ProviderError("submission_unknown", "结果不明", uncertain=True)
        return {"task_id": key, "status": "queued"}

    def query(self, remote_id):
        if self.query_error:
            raise ProviderError("query_failed", "查询失败")
        return {
            "task_id": remote_id,
            "status": self.results.get(remote_id, "succeeded"),
            "url": "https://example.com/result.png",
        }

    def download(self, url):
        if self.download_error:
            raise ProviderError("download_failed", "下载失败")
        return image_bytes()


def drain(worker, count=20):
    for _ in range(count):
        if not worker.step():
            break


def state(client, batch_id):
    with write_session(client.app.state.engine) as session:
        return session.get(GenerationBatch, batch_id).status, list(
            session.scalars(select(GenerationTask).where(GenerationTask.batch_id == batch_id))
        )


def test_single_result_and_restart_preserves_remote_ids(client):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "generating"
    assert client.get("/api/orders", params={"status": "generating"}).json()["total"] == 1
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        worker.step()
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert state(client, batch.id)[0] == "succeeded"
    assert len(provider.submits) == 1
    detail = client.get(f"/api/orders/{order_id}").json()
    assert detail["status"] == "review"
    outputs = [a for a in detail["assets"] if a["kind"] == "generated"]
    assert len(outputs) == 1
    assert all(client.get(a["content_url"]).content == image_bytes() for a in outputs)


def test_two_orders_run_independently(client):
    first_id, first_payload = ready(client)
    second_id, second_payload = ready(client)
    first = submit(client, first_id, first_payload, "first-order")
    second = submit(client, second_id, second_payload, "second-order")
    assert client.get("/api/orders", params={"status": "generating"}).json()["total"] == 2
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        worker.step()
        worker.step()
        assert len(provider.submits) == 2
        drain(worker)
    assert state(client, first.id)[0] == state(client, second.id)[0] == "succeeded"
    assert client.get("/api/orders", params={"status": "review"}).json()["total"] == 2


def test_new_schema_rejects_multiple_outputs(client):
    from sqlalchemy.exc import IntegrityError

    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    with pytest.raises(IntegrityError), write_session(client.app.state.engine) as session:
        session.get(GenerationBatch, batch.id).target_count = 2
    with pytest.raises(IntegrityError), write_session(client.app.state.engine) as session:
        make_task(session, session.get(GenerationBatch, batch.id), 1)


def test_query_and_download_do_not_regenerate(client):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    provider = FakeProvider()
    provider.query_error = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker, 8)
        assert all(t.status in {"pending", "queued"} for t in state(client, batch.id)[1])
        provider.query_error = False
        provider.download_error = True
        drain(worker)
        assert state(client, batch.id)[0] == "failed"
        assert client.get(f"/api/orders/{order_id}").json()["status"] == "draft"
        rows = client.get("/api/orders", params={"status": "draft"}).json()["items"]
        assert rows[0]["last_batch_status"] == "failed"
        provider.download_error = False
        with write_session(client.app.state.engine) as session:
            retry_batch(session, batch.id, RetryRequest(slot_indices=[0]), "download-again")
        assert client.get(f"/api/orders/{order_id}").json()["status"] == "generating"
        drain(worker)
    assert state(client, batch.id)[0] == "succeeded"
    assert len(provider.submits) == 1


def test_crash_and_unknown_never_resubmit(client):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    with write_session(client.app.state.engine) as session:
        task = session.scalar(select(GenerationTask).where(GenerationTask.batch_id == batch.id))
        task.status = "submitting"
    provider = FakeProvider()
    provider.unknown = True
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
        assert state(client, batch.id)[0] == "needs_attention"
        assert client.get(f"/api/orders/{order_id}").json()["status"] == "generating"
        row = client.get("/api/orders").json()["items"][0]
        assert row["last_batch_status"] == "needs_attention"
        assert len(provider.submits) == 0
        with pytest.raises(RuntimeError, match="已有 Worker"):
            with Worker(client.app.state.settings, FakeProvider()):
                pass
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert len(provider.submits) == 0
