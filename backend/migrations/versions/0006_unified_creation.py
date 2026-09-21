"""创建统一创作新表，保留全部旧结构和数据，不转换历史订单。"""

from alembic import op

revision = "0006_unified_creation"
down_revision = "0005_single_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE v2_orders (
        id VARCHAR(36) NOT NULL,
        order_no VARCHAR(64) NOT NULL,
        customer_name VARCHAR(100) NOT NULL,
        note VARCHAR(2000) NOT NULL,
        source_channel VARCHAR(40) NOT NULL,
        style_id VARCHAR(40) NOT NULL,
        status VARCHAR(24) NOT NULL,
        params_json JSON NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT v2_ck_orders_status CHECK (status IN
        ('draft','ready','review','revision_requested','completed','closed')),
        UNIQUE (order_no)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX v2_ix_orders_status_created ON v2_orders (status, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE v2_assets (
        id VARCHAR(36) NOT NULL,
        order_id VARCHAR(36) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        input_role VARCHAR(20),
        is_active_input BOOLEAN NOT NULL,
        generation_task_id VARCHAR(36),
        relative_path VARCHAR(255) NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        mime_type VARCHAR(40) NOT NULL,
        byte_size INTEGER NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        review_status VARCHAR(20) NOT NULL,
        sort_index INTEGER NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT v2_ck_assets_kind CHECK (kind IN ('input','generated')),
        CONSTRAINT v2_ck_assets_role CHECK ((kind='input' AND input_role IN
        ('main','material')) OR (kind='generated' AND input_role IS NULL AND
        is_active_input=0)),
        FOREIGN KEY(order_id) REFERENCES v2_orders (id),
        UNIQUE (generation_task_id),
        CONSTRAINT v2_fk_assets_generation_task FOREIGN KEY(generation_task_id) REFERENCES
        v2_generation_tasks (id),
        UNIQUE (relative_path)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX v2_ix_assets_order_id ON v2_assets (order_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX v2_uq_assets_active_role ON v2_assets (order_id, input_role)
        WHERE is_active_input=1 AND input_role IN ('main')
        """
    )
    op.execute(
        """
        CREATE TABLE v2_generation_batches (
        id VARCHAR(36) NOT NULL,
        order_id VARCHAR(36) NOT NULL,
        operation VARCHAR(16) NOT NULL,
        base_asset_id VARCHAR(36),
        revision_instruction VARCHAR(2000),
        target_count INTEGER NOT NULL,
        status VARCHAR(24) NOT NULL,
        request_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        input_snapshot_json JSON NOT NULL,
        params_snapshot_json JSON NOT NULL,
        style_snapshot_json JSON NOT NULL,
        prompt_snapshot VARCHAR NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        finished_at VARCHAR(40),
        PRIMARY KEY (id),
        CONSTRAINT v2_uq_batch_request UNIQUE (order_id, operation, request_key),
        CONSTRAINT v2_ck_batch_target CHECK ((operation='initial' AND target_count=1) OR
        (operation='revision' AND target_count=1)),
        FOREIGN KEY(order_id) REFERENCES v2_orders (id),
        FOREIGN KEY(base_asset_id) REFERENCES v2_assets (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX v2_ix_batches_order_created ON v2_generation_batches (order_id,
        created_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX v2_uq_batch_open_order ON v2_generation_batches (order_id) WHERE
        status IN ('pending','running','needs_attention')
        """
    )
    op.execute(
        """
        CREATE TABLE v2_generation_tasks (
        id VARCHAR(36) NOT NULL,
        batch_id VARCHAR(36) NOT NULL,
        slot_index INTEGER NOT NULL,
        attempt_no INTEGER NOT NULL,
        status VARCHAR(24) NOT NULL,
        provider VARCHAR(40) NOT NULL,
        model VARCHAR(80) NOT NULL,
        provider_task_id VARCHAR(128),
        provider_idempotency_key VARCHAR(128) NOT NULL,
        request_snapshot_json JSON NOT NULL,
        result_metadata_json JSON NOT NULL,
        error_code VARCHAR(80),
        error_message VARCHAR(500),
        failure_stage VARCHAR(20),
        resolution_json JSON NOT NULL,
        next_poll_at VARCHAR(40),
        claimed_at VARCHAR(40),
        submitted_at VARCHAR(40),
        finished_at VARCHAR(40),
        poll_failures INTEGER NOT NULL,
        cost_amount VARCHAR(40),
        cost_currency VARCHAR(16),
        cost_source VARCHAR(255),
        PRIMARY KEY (id),
        CONSTRAINT v2_uq_task_attempt UNIQUE (batch_id, slot_index, attempt_no),
        CONSTRAINT v2_ck_task_slot_attempt CHECK (slot_index=0 AND attempt_no>=1),
        FOREIGN KEY(batch_id) REFERENCES v2_generation_batches (id),
        UNIQUE (provider_task_id),
        UNIQUE (provider_idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX v2_ix_tasks_poll ON v2_generation_tasks (status, next_poll_at)
        """
    )
    op.execute(
        """
        CREATE TABLE v2_generation_actions (
        id VARCHAR(36) NOT NULL,
        scope VARCHAR(100) NOT NULL,
        request_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        batch_id VARCHAR(36) NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT v2_uq_action_request UNIQUE (scope, request_key),
        FOREIGN KEY(batch_id) REFERENCES v2_generation_batches (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE v2_order_deliveries (
        id VARCHAR(36) NOT NULL,
        order_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        sort_index INTEGER NOT NULL,
        selected_at VARCHAR(40) NOT NULL,
        revoked_at VARCHAR(40),
        last_exported_at VARCHAR(40),
        PRIMARY KEY (id),
        CONSTRAINT v2_ck_delivery_sort CHECK (sort_index >= 0),
        FOREIGN KEY(order_id) REFERENCES v2_orders (id),
        FOREIGN KEY(asset_id) REFERENCES v2_assets (id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX v2_uq_delivery_active ON v2_order_deliveries (order_id) WHERE
        revoked_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX v2_ix_deliveries_order ON v2_order_deliveries (order_id)
        """
    )
    op.execute(
        """
        CREATE TRIGGER v2_assets_limit_insert BEFORE INSERT ON v2_assets WHEN
        NEW.kind='input' AND NEW.is_active_input=1 AND (SELECT count(*) FROM v2_assets WHERE
        order_id=NEW.order_id AND kind='input' AND is_active_input=1 AND id!=NEW.id)>=4
        BEGIN SELECT RAISE(ABORT, 'active input limit'); END
        """
    )
    op.execute(
        """
        CREATE TRIGGER v2_assets_limit_update BEFORE UPDATE ON v2_assets WHEN
        NEW.kind='input' AND NEW.is_active_input=1 AND (SELECT count(*) FROM v2_assets WHERE
        order_id=NEW.order_id AND kind='input' AND is_active_input=1 AND id!=NEW.id)>=4
        BEGIN SELECT RAISE(ABORT, 'active input limit'); END
        """
    )


def downgrade() -> None:
    raise RuntimeError("新流程不提供破坏性回退；旧数据仍独立保留")
