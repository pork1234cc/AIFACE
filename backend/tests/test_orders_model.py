"""使用真实迁移验证约束以及业务数据在重复迁移后保留。"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import PROJECT_ROOT, Settings
from app.db import create_db_engine, session_scope
from app.models.orders import Asset, Order


def test_business_migration_and_unlimited_materials(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "orders.sqlite3"))
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "head")
    engine = create_db_engine(Settings(_env_file=None))
    try:
        with session_scope(engine) as session:
            order = Order(customer_name="中文客户", order_no="TEST-001")
            session.add(order)
            session.flush()
            order_id = order.id

        def insert_asset(role="material", active=True):
            with session_scope(engine) as session:
                asset = Asset(
                    order_id=order_id,
                    input_role=role,
                    relative_path=str(__import__("uuid").uuid4()),
                    original_name="照片.png",
                    mime_type="image/png",
                    byte_size=1,
                    width=1,
                    height=1,
                    sha256="0" * 64,
                    is_active_input=active,
                )
                session.add(asset)

        insert_asset("main")
        with pytest.raises(IntegrityError):
            insert_asset("main")
        insert_asset("material")
        insert_asset()
        insert_asset()
        insert_asset()
        insert_asset(active=False)
        command.upgrade(config, "head")
        with session_scope(engine) as session:
            assert session.get(Order, order_id).customer_name == "中文客户"
            assert len(session.scalars(select(Asset)).all()) == 6
    finally:
        engine.dispose()
