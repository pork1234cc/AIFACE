"""迁移保留原数据、结果文件提交中断及历史快照恢复。"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from test_generation_service import ready, submit
from test_orders_api import client as api_client
from test_worker import FakeProvider, drain, state

from app.config import PROJECT_ROOT, Settings
from app.db import create_db_engine
from app.models.orders import GenerationBatch, Order
from app.services.assets import decode_upload
from app.services.orders import get_order, write_session
from app.worker import Worker

client = api_client


def test_order_status_migration_preserves_existing_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "lifecycle.sqlite3"))
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "0009_unlimited_materials")
    engine = create_db_engine(Settings(_env_file=None))
    with write_session(engine) as session:
        for order_id, status in (
            ("unsubmitted", "ready"),
            ("first", "ready"),
            ("revision", "review"),
            ("failed-revision", "revision_requested"),
        ):
            session.add(Order(
                id=order_id, order_no=f"AF-{order_id}",
                customer_name=order_id, status=status,
            ))
        session.flush()
        for order_id, operation in (("first", "initial"), ("revision", "revision")):
            session.add(GenerationBatch(
                order_id=order_id, operation=operation, status="running",
                request_key=order_id, request_hash="hash", input_snapshot_json=[],
                params_snapshot_json={}, style_snapshot_json={}, prompt_snapshot="测试",
            ))
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_db_engine(Settings(_env_file=None))
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id, status FROM v2_orders"))
        statuses = {row.id: row.status for row in rows}
        assert statuses == {
            "unsubmitted": "draft", "first": "generating",
            "revision": "modifying", "failed-revision": "review",
        }
        assert list(connection.execute(text("PRAGMA foreign_key_check"))) == []
    engine.dispose()


def test_upgrade_existing_stage2_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "legacy.sqlite3"))
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "0002_orders_assets")
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO orders VALUES "
                "('old','AF-old','旧客户','保留备注','test','q_crayon_001','draft','{}','now','now')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO assets VALUES "
                "('photo','old','input','person_main',1,NULL,'orders/old/photo.png','旧照片.png',"
                "'image/png',1,1,1,'hash','unreviewed',0,'now')"
            )
        )
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT customer_name FROM orders")) == "旧客户"
        assert conn.scalar(text("SELECT original_name FROM assets")) == "旧照片.png"
        assert conn.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger'")) == 2
        assert conn.scalar(text("SELECT count(*) FROM v2_orders")) == 0
        assert list(conn.execute(text("PRAGMA foreign_key_check"))) == []
    engine.dispose()


def test_snapshot_uses_removed_input_after_current_changes(client):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    client.patch(
        f"/api/orders/{order_id}/images/{payload.config.base_asset_id}/active",
        json={"active": False},
    ).raise_for_status()
    provider = FakeProvider()
    original_submit = provider.submit

    def inspect(snapshot, images, key):
        assert "后来改动" not in snapshot["prompt"]
        assert len(images) == 1
        return original_submit(snapshot, images, key)

    provider.submit = inspect
    with write_session(client.app.state.engine) as session:
        order = get_order(session, order_id)
        order.params_json = order.params_json | {"extra_requirement": "后来改动"}
    with Worker(client.app.state.settings, provider, 0) as worker:
        drain(worker)
    assert state(client, batch.id)[0] == "succeeded"


def test_existing_output_file_is_reused_without_overwrite(client, monkeypatch):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    provider = FakeProvider()
    with Worker(client.app.state.settings, provider, 0) as worker:
        while True:
            worker.step()
            _, tasks = state(client, batch.id)
            downloading = [t for t in tasks if t.status == "downloading"]
            if downloading:
                task = downloading[0]
                break
        import io

        data, extension, _, _, _ = decode_upload(io.BytesIO(provider.download("")))
        target = client.app.state.settings.storage_path / (
            f"orders/{order_id}/generated/{task.id}.{extension}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        before = target.stat().st_mtime_ns
        drain(worker)
        assert target.stat().st_mtime_ns == before
    assert state(client, batch.id)[0] == "succeeded"


def test_persist_failure_can_resume_same_remote_task(client, monkeypatch):
    order_id, payload = ready(client)
    batch = submit(client, order_id, payload)
    provider = FakeProvider()
    original = Path.rename

    def fail_rename(path, target):
        raise OSError("模拟磁盘写入中断")

    with Worker(client.app.state.settings, provider, 0) as worker:
        monkeypatch.setattr(Path, "rename", fail_rename)
        drain(worker)
        status, tasks = state(client, batch.id)
        assert status == "failed"
        assert all(t.failure_stage == "persist" for t in tasks)
        monkeypatch.setattr(Path, "rename", original)
        response = client.post(
            f"/api/batches/{batch.id}/retry",
            json={"slot_indices": [0]},
            headers={"Idempotency-Key": "persist-retry"},
        )
        assert response.status_code == 202
        drain(worker)
    assert state(client, batch.id)[0] == "succeeded"
    assert len(provider.submits) == 1
