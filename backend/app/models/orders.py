"""订单与素材模型，历史图片保留，不级联删除。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_params() -> dict:
    from app.schemas.orders import Params

    return Params().model_dump()


class CustomStyle(Base):
    __tablename__ = "v2_custom_styles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(String(4000))
    version: Mapped[int] = mapped_column(Integer, default=1)
    preview_task_id: Mapped[str | None] = mapped_column(String(36))
    cover_task_id: Mapped[str | None] = mapped_column(String(36))
    cover_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class StylePreviewTask(Base):
    __tablename__ = "v2_style_preview_tasks"
    __table_args__ = (
        UniqueConstraint("style_id", "idempotency_key", name="v2_uq_style_preview_key"),
        Index(
            "v2_uq_style_preview_active",
            "style_id",
            unique=True,
            sqlite_where=text(
                "status IN ('pending','submitting','queued','running',"
                "'downloading','submission_unknown')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    style_id: Mapped[str] = mapped_column(ForeignKey("v2_custom_styles.id"))
    style_version: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_snapshot_json: Mapped[dict] = mapped_column(JSON)
    reference_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    provider_task_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    download_url: Mapped[str | None] = mapped_column(String(8192))
    relative_path: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    next_poll_at: Mapped[str | None] = mapped_column(String(40))
    poll_failures: Mapped[int] = mapped_column(Integer, default=0)
    reconcile_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class Order(Base):
    __tablename__ = "v2_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','generating','modifying','review','completed','closed')",
            name="v2_ck_orders_status",
        ),
        Index("v2_ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_no: Mapped[str] = mapped_column(String(64), unique=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(String(2000), default="")
    source_channel: Mapped[str] = mapped_column(String(40), default="xiaohongshu")
    style_id: Mapped[str] = mapped_column(String(40), default="q_crayon_001")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    params_json: Mapped[dict] = mapped_column(JSON, default=default_params)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class Asset(Base):
    __tablename__ = "v2_assets"
    __table_args__ = (
        CheckConstraint("kind IN ('input','generated')", name="v2_ck_assets_kind"),
        CheckConstraint(
            "(kind='input' AND input_role IN ('main','material')) OR "
            "(kind='generated' AND input_role IS NULL AND is_active_input=0)",
            name="v2_ck_assets_role",
        ),
        Index("v2_ix_assets_order_id", "order_id"),
        Index(
            "v2_uq_assets_active_role",
            "order_id",
            "input_role",
            unique=True,
            sqlite_where=text("is_active_input=1 AND input_role IN ('main')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("v2_orders.id"))
    kind: Mapped[str] = mapped_column(String(16), default="input")
    input_role: Mapped[str | None] = mapped_column(String(20))
    is_active_input: Mapped[bool] = mapped_column(Boolean, default=True)
    generation_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("v2_generation_tasks.id", name="v2_fk_assets_generation_task"), unique=True
    )
    relative_path: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(40))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class GenerationBatch(Base):
    __tablename__ = "v2_generation_batches"
    __table_args__ = (
        UniqueConstraint("order_id", "operation", "request_key", name="v2_uq_batch_request"),
        CheckConstraint(
            "(operation='initial' AND target_count=1) OR (operation='revision' AND target_count=1)",
            name="v2_ck_batch_target",
        ),
        Index("v2_ix_batches_order_created", "order_id", "created_at"),
        Index(
            "v2_uq_batch_open_order",
            "order_id",
            unique=True,
            sqlite_where=text("status IN ('pending','running','needs_attention')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("v2_orders.id"))
    operation: Mapped[str] = mapped_column(String(16), default="initial")
    base_asset_id: Mapped[str | None] = mapped_column(ForeignKey("v2_assets.id", use_alter=True))
    revision_instruction: Mapped[str | None] = mapped_column(String(2000))
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    request_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot_json: Mapped[list] = mapped_column(JSON)
    params_snapshot_json: Mapped[dict] = mapped_column(JSON)
    style_snapshot_json: Mapped[dict] = mapped_column(JSON)
    prompt_snapshot: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    finished_at: Mapped[str | None] = mapped_column(String(40))


class GenerationTask(Base):
    __tablename__ = "v2_generation_tasks"
    __table_args__ = (
        UniqueConstraint("batch_id", "slot_index", "attempt_no", name="v2_uq_task_attempt"),
        CheckConstraint("slot_index=0 AND attempt_no>=1", name="v2_ck_task_slot_attempt"),
        Index("v2_ix_tasks_poll", "status", "next_poll_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_batches.id"))
    slot_index: Mapped[int] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    provider: Mapped[str] = mapped_column(String(40), default="apii")
    model: Mapped[str] = mapped_column(String(80), default="gpt-image-2.0-4k")
    provider_task_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    provider_idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, default=new_id)
    request_snapshot_json: Mapped[dict] = mapped_column(JSON)
    result_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    failure_stage: Mapped[str | None] = mapped_column(String(20))
    resolution_json: Mapped[dict] = mapped_column(JSON, default=dict)
    next_poll_at: Mapped[str | None] = mapped_column(String(40))
    claimed_at: Mapped[str | None] = mapped_column(String(40))
    submitted_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    poll_failures: Mapped[int] = mapped_column(Integer, default=0)
    cost_amount: Mapped[str | None] = mapped_column(String(40))
    cost_currency: Mapped[str | None] = mapped_column(String(16))
    cost_source: Mapped[str | None] = mapped_column(String(255))


class GenerationAction(Base):
    """补生成与人工核对的持久化幂等记录。"""

    __tablename__ = "v2_generation_actions"
    __table_args__ = (UniqueConstraint("scope", "request_key", name="v2_uq_action_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(100))
    request_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_batches.id"))
    created_at: Mapped[str] = mapped_column(String(40), default=utc_now)


class OrderDelivery(Base):
    """最终图选择历史；撤销保留记录，导出不改变订单业务状态。"""

    __tablename__ = "v2_order_deliveries"
    __table_args__ = (
        Index("v2_ix_deliveries_order", "order_id"),
        Index(
            "v2_uq_delivery_active",
            "order_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
        ),
        CheckConstraint("sort_index >= 0", name="v2_ck_delivery_sort"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("v2_orders.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("v2_assets.id"))
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    selected_at: Mapped[str] = mapped_column(String(40), default=utc_now)
    revoked_at: Mapped[str | None] = mapped_column(String(40))
    last_exported_at: Mapped[str | None] = mapped_column(String(40))
