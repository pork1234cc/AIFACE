"""基于已保存结果修改，明确输入和历史来源，不重复施加旧控制项。"""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orders import Asset, GenerationBatch, GenerationTask, OrderDelivery, utc_now
from app.schemas.generation import ReviewRequest, RevisionRequest
from app.services.generation import (
    aggregate,
    ensure_available,
    make_task,
    preview_creation,
    request_hash,
    verify_input,
)
from app.services.orders import BusinessError, get_assets, get_order


def available_result(session: Session, order_id: str, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None or asset.order_id != order_id or asset.kind != "generated":
        raise BusinessError(422, "invalid_base", "基础图须为本订单生成结果")
    task = session.get(GenerationTask, asset.generation_task_id)
    if asset.review_status == "discarded" or task is None or task.status != "succeeded":
        raise BusinessError(409, "base_unavailable", "基础图须已成功保存且未作废")
    return asset


def create_revision(
    session: Session, storage: Path, order_id: str, payload: RevisionRequest, key: str
) -> GenerationBatch:
    normalized = payload.model_dump()
    digest = request_hash(normalized)
    existing = session.scalar(
        select(GenerationBatch).where(
            GenerationBatch.order_id == order_id,
            GenerationBatch.operation == "revision",
            GenerationBatch.request_key == key,
        )
    )
    if existing:
        if existing.request_hash != digest:
            raise BusinessError(409, "idempotency_conflict", "同一请求编号不能用于不同内容")
        return existing
    ensure_available(session, order_id)
    base = available_result(session, order_id, payload.config.base_asset_id)
    current = session.scalar(
        select(OrderDelivery.asset_id).where(
            OrderDelivery.order_id == order_id, OrderDelivery.revoked_at.is_(None)
        )
    )
    if current != base.id:
        raise BusinessError(409, "base_changed", "本次底图必须是当前交付图，请刷新后核对版本")
    assets = get_assets(session, order_id)
    preview = preview_creation(session, storage, order_id, payload, "revision")
    by_id = {a.id: a for a in assets}
    selected = [(by_id[item["asset_id"]], item["role"]) for item in preview["inputs"]]
    snapshots = []
    for asset, role in selected:
        verify_input(storage, asset)
        snapshots.append(
            {
                "asset_id": asset.id,
                "role": role,
                **{
                    field: getattr(asset, field)
                    for field in (
                        "relative_path",
                        "mime_type",
                        "sha256",
                        "byte_size",
                        "width",
                        "height",
                    )
                },
            }
        )
    batch = GenerationBatch(
        order_id=order_id,
        operation="revision",
        target_count=1,
        base_asset_id=base.id,
        revision_instruction=payload.config.extra_requirement,
        request_key=key,
        request_hash=digest,
        input_snapshot_json=snapshots,
        params_snapshot_json=preview["params"],
        style_snapshot_json=preview["style"],
        prompt_snapshot=preview["prompt"],
    )
    session.add(batch)
    session.flush()
    make_task(session, batch, 0)
    aggregate(session, batch)
    return batch


def review_result(session: Session, asset_id: str, payload: ReviewRequest) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise BusinessError(404, "asset_not_found", "图片不存在")
    order = get_order(session, asset.order_id, editable=True)
    if asset.kind != "generated":
        raise BusinessError(422, "not_generated", "仅生成结果可以入选或作废")
    if payload.review_status == "discarded" and session.scalar(
        select(OrderDelivery.id).where(
            OrderDelivery.asset_id == asset_id, OrderDelivery.revoked_at.is_(None)
        )
    ):
        raise BusinessError(409, "current_delivery", "当前交付图不能作废，请先切换或撤销交付选择")
    asset.review_status = payload.review_status
    order.updated_at = utc_now()
    return asset


def request_revision(session: Session, order_id: str):
    ensure_available(session, order_id)
    available = session.scalar(
        select(Asset.id)
        .join(GenerationTask, Asset.generation_task_id == GenerationTask.id)
        .where(
            Asset.order_id == order_id,
            Asset.kind == "generated",
            Asset.review_status != "discarded",
            GenerationTask.status == "succeeded",
        )
    )
    if available is None:
        raise BusinessError(409, "no_result", "需要至少一张可用结果才能继续修改")
    # 进入编辑不改变订单阶段；提交修改任务时才切换为“修改中”。
    return get_order(session, order_id)


def revision_stats(session: Session, order_id: str) -> dict:
    counts = dict(
        session.execute(
            select(GenerationBatch.status, func.count())
            .where(GenerationBatch.order_id == order_id, GenerationBatch.operation == "revision")
            .group_by(GenerationBatch.status)
        ).all()
    )
    attempts, submissions = session.execute(
        select(func.count(GenerationTask.id), func.count(GenerationTask.submitted_at))
        .join(GenerationBatch)
        .where(GenerationBatch.order_id == order_id)
    ).one()
    return {
        "revision_count": sum(counts.values()),
        "successful_revision_count": counts.get("succeeded", 0),
        "generation_attempt_count": attempts,
        "submitted_attempt_count": submissions,
    }
