"""新增独立风格示意图任务，保留旧封面及全部订单数据。"""

import sqlalchemy as sa
from alembic import op

revision = "0008_style_previews"
down_revision = "0007_custom_styles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("v2_custom_styles", sa.Column("preview_task_id", sa.String(36)))
    op.add_column("v2_custom_styles", sa.Column("cover_task_id", sa.String(36)))
    op.add_column("v2_custom_styles", sa.Column("cover_version", sa.Integer()))
    op.create_table(
        "v2_style_preview_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("style_id", sa.String(40), sa.ForeignKey("v2_custom_styles.id"), nullable=False),
        sa.Column("style_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("reference_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_task_id", sa.String(128), unique=True),
        sa.Column("download_url", sa.String(8192)),
        sa.Column("relative_path", sa.String(255)),
        sa.Column("mime_type", sa.String(40)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("next_poll_at", sa.String(40)),
        sa.Column("poll_failures", sa.Integer(), nullable=False),
        sa.Column("reconcile_note", sa.String(1000)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("style_id", "idempotency_key", name="v2_uq_style_preview_key"),
    )
    op.create_index(
        "v2_uq_style_preview_active",
        "v2_style_preview_tasks",
        ["style_id"],
        unique=True,
        sqlite_where=sa.text(
            "status IN ('pending','submitting','queued','running',"
            "'downloading','submission_unknown')"
        ),
    )


def downgrade() -> None:
    raise RuntimeError("示意图任务可能已计费且被风格引用，不支持自动删除降级")
