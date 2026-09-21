"""新增自定义风格，不修改内置风格及历史快照。"""

import sqlalchemy as sa
from alembic import op

revision = "0007_custom_styles"
down_revision = "0006_unified_creation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_custom_styles",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("prompt", sa.String(4000), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("自定义风格可能已被订单引用，不支持自动降级删除")
