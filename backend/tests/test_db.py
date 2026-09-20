"""验证迁移幂等、外键约束和事务回滚。"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import PROJECT_ROOT, Settings
from app.db import create_db_engine, session_scope


def test_migration_can_run_twice_without_changing_existing_data(tmp_path, monkeypatch):
    database_path = tmp_path / "中文数据" / "aiface.sqlite3"
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(database_path))
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    command.upgrade(config, "head")
    engine = create_db_engine(Settings(_env_file=None))
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE preserved (value TEXT)"))
            connection.execute(text("INSERT INTO preserved VALUES ('保留数据')"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert connection.scalar(text("SELECT value FROM preserved")) == "保留数据"
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_foreign_keys_and_transaction_rollback(tmp_path):
    settings = Settings(_env_file=None, AIFACE_DATABASE_PATH=tmp_path / "test.sqlite3")
    engine = create_db_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"))
        with pytest.raises(IntegrityError), session_scope(engine) as session:
            session.execute(text("INSERT INTO parent VALUES (1)"))
            session.execute(text("INSERT INTO child VALUES (99)"))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM parent")) == 0
    finally:
        engine.dispose()
