"""增加最终交付选择，旧订单、素材和生成历史保持不变。"""

import sqlalchemy as sa
from alembic import op

revision = "0004_deliveries"
down_revision = "0003_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("selected_at", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.String(40)),
        sa.Column("last_exported_at", sa.String(40)),
        sa.CheckConstraint("sort_index >= 0", name="ck_delivery_sort"),
    )
    op.create_index("ix_deliveries_order", "order_deliveries", ["order_id"])
    op.create_index(
        "uq_delivery_active",
        "order_deliveries",
        ["order_id"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("交付历史不提供破坏性自动回退，请使用已确认的备份恢复流程")
