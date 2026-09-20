"""迁移复用应用配置，避免写入另一份数据库。"""

from alembic import context
from sqlalchemy import URL

from app.config import Settings
from app.db import Base, create_db_engine
from app.models import orders  # noqa: F401 — 注册业务模型元数据供迁移比较使用。

settings = Settings()

if context.is_offline_mode():
    context.configure(
        url=URL.create("sqlite", database=str(settings.database_path)),
        target_metadata=Base.metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
