"""建立订单和图片表，不修改已有基线。"""

import sqlalchemy as sa
from alembic import op

revision = "0002_orders_assets"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_no", sa.String(64), nullable=False, unique=True),
        sa.Column("customer_name", sa.String(100), nullable=False),
        sa.Column("note", sa.String(2000), nullable=False),
        sa.Column("source_channel", sa.String(40), nullable=False),
        sa.Column("style_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','ready','review','revision_requested','completed','closed')",
            name="ck_orders_status",
        ),
    )
    op.create_index("ix_orders_status_created", "orders", ["status", "created_at"])
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("input_role", sa.String(20)),
        sa.Column("is_active_input", sa.Boolean(), nullable=False),
        sa.Column("generation_task_id", sa.String(36), unique=True),
        sa.Column("relative_path", sa.String(255), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("kind IN ('input','generated')", name="ck_assets_kind"),
        sa.CheckConstraint(
            "(kind='input' AND input_role IN ('person_main','person_aux','reference')) OR "
            "(kind='generated' AND input_role IS NULL AND is_active_input=0)",
            name="ck_assets_role",
        ),
    )
    op.create_index("ix_assets_order_id", "assets", ["order_id"])
    op.create_index(
        "uq_assets_active_role",
        "assets",
        ["order_id", "input_role"],
        unique=True,
        sqlite_where=sa.text("is_active_input=1 AND input_role IN ('person_main','reference')"),
    )
    for action in ("INSERT", "UPDATE"):
        op.execute(f"""
            CREATE TRIGGER assets_limit_{action.lower()} BEFORE {action} ON assets
            WHEN NEW.is_active_input=1 AND
              (SELECT count(*) FROM assets WHERE order_id=NEW.order_id
               AND is_active_input=1 AND id<>NEW.id)>=4
            BEGIN SELECT RAISE(ABORT, 'active_input_limit'); END
        """)


def downgrade() -> None:
    op.drop_table("assets")
    op.drop_table("orders")
