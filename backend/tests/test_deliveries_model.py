"""旧库升级保留数据及最终选择唯一约束。"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import PROJECT_ROOT, Settings
from app.db import create_db_engine
from app.models.orders import Asset, GenerationBatch, GenerationTask, Order, OrderDelivery
from app.services.orders import write_session


def test_migration_preserves_data_and_active_selection_unique(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "migration.sqlite3"))
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "0003_generation")
    engine = create_db_engine(Settings(_env_file=None))
    with write_session(engine) as session:
        order = Order(order_no="OLD-ORDER", customer_name="旧客户")
        session.add(order)
        session.flush()
        asset = Asset(
            order_id=order.id,
            input_role="person_main",
            relative_path="old.png",
            original_name="旧素材.png",
            mime_type="image/png",
            byte_size=1,
            width=1,
            height=1,
            sha256="0" * 64,
        )
        session.add(asset)
        session.flush()
        legacy = GenerationBatch(
            order_id=order.id,
            target_count=2,
            status="succeeded",
            request_key="legacy-two",
            request_hash="hash",
            input_snapshot_json=[],
            params_snapshot_json={},
            style_snapshot_json={},
            prompt_snapshot="旧双图提示词",
        )
        session.add(legacy)
        session.flush()
        task = GenerationTask(
            batch_id=legacy.id, slot_index=1, status="succeeded", request_snapshot_json={}
        )
        session.add(task)
        session.flush()
        output = Asset(
            order_id=order.id,
            kind="generated",
            input_role=None,
            is_active_input=False,
            generation_task_id=task.id,
            relative_path="generated.png",
            original_name="旧结果.png",
            mime_type="image/png",
            byte_size=1,
            width=1,
            height=1,
            sha256="0" * 64,
        )
        session.add(output)
    command.upgrade(config, "head")
    command.check(config)
    command.upgrade(config, "head")
    with write_session(engine) as session:
        assert session.get(Order, order.id).customer_name == "旧客户"
        assert session.get(Asset, asset.id).original_name == "旧素材.png"
        assert session.get(GenerationBatch, legacy.id).target_count == 2
        assert session.get(Asset, output.id).generation_task_id == task.id
        assert session.get(GenerationTask, task.id).slot_index == 1
        assert not session.execute(text("PRAGMA foreign_key_check")).all()
        assert session.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger'")) == 2
        session.add(OrderDelivery(order_id=order.id, asset_id=asset.id))
    with pytest.raises(IntegrityError), write_session(engine) as session:
        session.add(OrderDelivery(order_id=order.id, asset_id=asset.id))
    with write_session(engine) as session:
        session.add(OrderDelivery(order_id=order.id, asset_id=asset.id, revoked_at="2026-01-01"))
    engine.dispose()
