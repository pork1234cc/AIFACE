"""建立生成任务、快照和幂等记录，保留既有素材及额度触发器。"""

import sqlalchemy as sa
from alembic import op

revision = "0003_generation"
down_revision = "0002_orders_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("base_asset_id", sa.String(36), sa.ForeignKey("assets.id")),
        sa.Column("revision_instruction", sa.String(2000)),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("params_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("style_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("prompt_snapshot", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("finished_at", sa.String(40)),
        sa.UniqueConstraint("order_id", "operation", "request_key", name="uq_batch_request"),
        sa.CheckConstraint(
            "(operation='initial' AND target_count=2) OR (operation='revision' AND target_count=1)",
            name="ck_batch_target",
        ),
    )
    op.create_index("ix_batches_order_created", "generation_batches", ["order_id", "created_at"])
    op.create_index(
        "uq_batch_open_order",
        "generation_batches",
        ["order_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending','running','needs_attention')"),
    )
    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id", sa.String(36), sa.ForeignKey("generation_batches.id"), nullable=False
        ),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("provider_task_id", sa.String(128), unique=True),
        sa.Column("provider_idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("request_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("result_metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("failure_stage", sa.String(20)),
        sa.Column("resolution_json", sa.JSON(), nullable=False),
        sa.Column("next_poll_at", sa.String(40)),
        sa.Column("claimed_at", sa.String(40)),
        sa.Column("submitted_at", sa.String(40)),
        sa.Column("finished_at", sa.String(40)),
        sa.Column("poll_failures", sa.Integer(), nullable=False),
        sa.Column("cost_amount", sa.String(40)),
        sa.Column("cost_currency", sa.String(16)),
        sa.Column("cost_source", sa.String(255)),
        sa.UniqueConstraint("batch_id", "slot_index", "attempt_no", name="uq_task_attempt"),
        sa.CheckConstraint("slot_index IN (0,1) AND attempt_no>=1", name="ck_task_slot_attempt"),
    )
    op.create_index("ix_tasks_poll", "generation_tasks", ["status", "next_poll_at"])
    op.create_table(
        "generation_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "batch_id", sa.String(36), sa.ForeignKey("generation_batches.id"), nullable=False
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("scope", "request_key", name="uq_action_request"),
    )
    triggers = list(
        op.get_bind()
        .execute(
            sa.text("SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assets'")
        )
        .scalars()
    )
    with op.batch_alter_table("assets") as batch:
        batch.create_foreign_key(
            "fk_assets_generation_task", "generation_tasks", ["generation_task_id"], ["id"]
        )
    for sql in triggers:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("任务历史迁移不提供破坏性自动回退，请使用已确认的完整备份恢复流程")
