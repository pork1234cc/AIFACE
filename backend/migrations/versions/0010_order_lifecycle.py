"""按生成任务持久化订单生命周期状态。"""

from alembic import op

revision = "0010_order_lifecycle"
down_revision = "0009_unlimited_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
        raise RuntimeError("迁移订单状态前无法暂停 SQLite 外键检查")
    try:
        op.execute("UPDATE v2_orders SET status='draft' WHERE status='ready'")
        op.execute("UPDATE v2_orders SET status='review' WHERE status='revision_requested'")
        with op.batch_alter_table("v2_orders", recreate="always") as batch:
            batch.drop_constraint("v2_ck_orders_status", type_="check")
            batch.create_check_constraint(
                "v2_ck_orders_status",
                "status IN ('draft','generating','modifying','review','completed','closed')",
            )
        op.execute(
            """
            UPDATE v2_orders SET status='generating'
            WHERE status NOT IN ('completed','closed') AND EXISTS (
                SELECT 1 FROM v2_generation_batches AS b
                WHERE b.order_id=v2_orders.id AND b.operation='initial'
                  AND b.status IN ('pending','running','needs_attention')
            )
            """
        )
        op.execute(
            """
            UPDATE v2_orders SET status='modifying'
            WHERE status NOT IN ('completed','closed') AND EXISTS (
                SELECT 1 FROM v2_generation_batches AS b
                WHERE b.order_id=v2_orders.id AND b.operation='revision'
                  AND b.status IN ('pending','running','needs_attention')
            )
            """
        )
        if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("迁移订单状态后外键检查失败")
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("订单生命周期已写入新状态，不能自动降级")
