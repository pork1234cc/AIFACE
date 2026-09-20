"""新生成仅一张；保留旧双图任务及其外键历史。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_single_generation"
down_revision = "0004_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 重建被引用表须暂时关闭本连接的外键检查，完成后立即恢复并检查。
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("generation_batches", recreate="always") as batch:
            batch.drop_constraint("ck_batch_target", type_="check")
            batch.create_check_constraint(
                "ck_batch_target",
                "(operation='initial' AND target_count IN (1,2)) OR "
                "(operation='revision' AND target_count=1)",
            )
        if connection.execute(sa.text("PRAGMA foreign_key_check")).first() is not None:
            raise RuntimeError("迁移后外键校验失败，请核对备份")
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("单图流程迁移不提供破坏性回退，请使用已确认的备份恢复流程")
