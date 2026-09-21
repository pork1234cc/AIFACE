"""移除活动输入数量限制，保留唯一主图约束和既有资产。"""

from alembic import op

revision = "0009_unlimited_materials"
down_revision = "0008_style_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS v2_assets_limit_insert")
    op.execute("DROP TRIGGER IF EXISTS v2_assets_limit_update")


def downgrade() -> None:
    raise RuntimeError("已有多素材订单时不能恢复四图限制")
