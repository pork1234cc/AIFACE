"""基于已保存结果修改，明确输入和历史来源，不重复施加旧控制项。"""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orders import Asset, GenerationBatch, GenerationTask, OrderDelivery, utc_now
from app.schemas.generation import ReviewRequest, RevisionRequest
from app.services.generation import ensure_available, make_task, request_hash, verify_input
from app.services.orders import BusinessError, get_order


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
    normalized = payload.model_dump() | {"instruction": payload.instruction.strip()}
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
    base = available_result(session, order_id, payload.base_asset_id)
    task = session.get(GenerationTask, base.generation_task_id)
    source = session.get(GenerationBatch, task.batch_id)
    ids = [base.id] + [item.asset_id for item in payload.additional_inputs]
    if len(set(ids)) != len(ids):
        raise BusinessError(422, "duplicate_input", "输入图片不能重复")
    selected = [(base, "base")]
    for item in payload.additional_inputs:
        asset = session.get(Asset, item.asset_id)
        if (
            asset is None
            or asset.order_id != order_id
            or asset.kind != "input"
            or not asset.is_active_input
            or asset.input_role != item.role
        ):
            raise BusinessError(422, "invalid_input", "附加图片须属于本单当前素材且角色一致")
        selected.append((asset, item.role))
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
    template = source.style_snapshot_json["prompt_template"]
    prompt = "\n".join(
        [
            "请以图片 1 为基础，仅输出一张修改后的独立头像。",
            template["system_style"],
            template["render_rule"],
            template["negative_rule"],
            "保留基础图中未要求修改的人物特征、构图与风格。本次修改要求优先。",
            *[
                f"图片 {index} 是明确附加的{role}素材，仅在修改要求需要时参考。"
                for index, (_, role) in enumerate(selected[1:], 2)
            ],
            "本次修改要求：" + normalized["instruction"],
        ]
    )
    batch = GenerationBatch(
        order_id=order_id,
        operation="revision",
        target_count=1,
        base_asset_id=base.id,
        revision_instruction=normalized["instruction"],
        request_key=key,
        request_hash=digest,
        input_snapshot_json=snapshots,
        params_snapshot_json=source.params_snapshot_json,
        style_snapshot_json=source.style_snapshot_json,
        prompt_snapshot=prompt,
    )
    session.add(batch)
    session.flush()
    make_task(session, batch, 0)
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
        raise BusinessError(409, "no_result", "需要至少一张可用结果才能标记待修改")
    order = get_order(session, order_id)
    order.status, order.updated_at = "revision_requested", utc_now()
    return order


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
