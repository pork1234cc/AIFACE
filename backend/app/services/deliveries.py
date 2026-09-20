"""单张当前交付图、版本切换、下载与终态；旧版本始终保留。"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orders import Asset, GenerationBatch, GenerationTask, OrderDelivery, utc_now
from app.schemas.deliveries import FinalsRequest
from app.services.generation import OPEN_STATUSES, ensure_available, verify_input
from app.services.orders import BusinessError, asset_data, get_order

logger = logging.getLogger(__name__)


def current_selections(session: Session, order_id: str) -> list[OrderDelivery]:
    return list(
        session.scalars(
            select(OrderDelivery)
            .where(OrderDelivery.order_id == order_id, OrderDelivery.revoked_at.is_(None))
            .order_by(OrderDelivery.sort_index, OrderDelivery.id)
        )
    )


def result_assets(session: Session, order_id: str) -> dict[str, Asset]:
    return {
        asset.id: asset
        for asset in session.scalars(
            select(Asset)
            .join(GenerationTask, Asset.generation_task_id == GenerationTask.id)
            .where(
                Asset.order_id == order_id,
                Asset.kind == "generated",
                GenerationTask.status == "succeeded",
            )
            .order_by(Asset.created_at, Asset.id)
        )
    }


def validate_selection(assets: dict[str, Asset], ids: list[str]) -> list[Asset]:
    if len(ids) != len(set(ids)):
        raise BusinessError(422, "duplicate_final", "最终图不能重复选择")
    if any(
        asset_id not in assets or assets[asset_id].review_status == "discarded" for asset_id in ids
    ):
        raise BusinessError(422, "invalid_final", "最终图须为本单成功保存且未作废的结果")
    return [assets[asset_id] for asset_id in ids]


def finals_data(session: Session, order_id: str) -> dict:
    order = get_order(session, order_id)
    assets = result_assets(session, order_id)
    records = list(
        session.scalars(
            select(OrderDelivery)
            .where(OrderDelivery.order_id == order_id)
            .order_by(OrderDelivery.selected_at, OrderDelivery.id)
        )
    )
    active = sorted(
        (record for record in records if record.revoked_at is None),
        key=lambda record: (record.sort_index, record.id),
    )
    return {
        "order_id": order_id,
        "order_status": order.status,
        "has_open_tasks": session.scalar(
            select(GenerationBatch.id).where(
                GenerationBatch.order_id == order_id, GenerationBatch.status.in_(OPEN_STATUSES)
            )
        )
        is not None,
        "items": [
            {
                "delivery_id": record.id,
                "asset_id": record.asset_id,
                "selected_at": record.selected_at,
                "last_exported_at": record.last_exported_at,
            }
            for record in active
        ],
        "versions": [asset_data(asset) for asset in assets.values()],
        "history": [
            {
                "delivery_id": record.id,
                "asset_id": record.asset_id,
                "selected_at": record.selected_at,
                "revoked_at": record.revoked_at,
                "last_exported_at": record.last_exported_at,
            }
            for record in records
        ],
    }


def set_finals(session: Session, storage: Path, order_id: str, payload: FinalsRequest):
    order = get_order(session, order_id, editable=True)
    assets = validate_selection(result_assets(session, order_id), payload.asset_ids)
    for asset in assets:
        verify_input(storage, asset)
    previous = {record.asset_id: record for record in current_selections(session, order_id)}
    now = utc_now()
    for asset_id, record in previous.items():
        if asset_id not in payload.asset_ids:
            record.revoked_at = now
    # 先释放同单唯一的当前选择，仍处于同一事务中。
    session.flush()
    for index, asset_id in enumerate(payload.asset_ids):
        if asset_id in previous:
            previous[asset_id].sort_index = index
        else:
            session.add(
                OrderDelivery(
                    order_id=order_id, asset_id=asset_id, sort_index=index, selected_at=now
                )
            )
    order.updated_at = now
    session.flush()
    logger.info("最终选择已设置 order_id=%s count=%s", order_id, len(assets))


def finish_order(session: Session, storage: Path, order_id: str, status: str):
    if status not in {"completed", "closed"}:
        raise ValueError("不支持的订单终态")
    order = get_order(session, order_id)
    if order.status == status:
        return order
    ensure_available(session, order_id)
    if status == "completed":
        records = current_selections(session, order_id)
        if not records:
            raise BusinessError(409, "no_final", "需要一张有效交付图才能完成订单")
        assets = validate_selection(result_assets(session, order_id), [r.asset_id for r in records])
        for asset in assets:
            verify_input(storage, asset)
    order.status, order.updated_at = status, utc_now()
    logger.info("订单进入终态 order_id=%s status=%s", order_id, status)
    return order


@dataclass
class ExportPlan:
    order_id: str
    order_no: str
    selection_ids: list[str]
    assets: list[Asset]


@dataclass
class ExportFile:
    filename: str
    mime_type: str
    content: bytes


def plan_export(session: Session, order_id: str) -> ExportPlan:
    order = get_order(session, order_id)
    records = current_selections(session, order_id)
    if not records:
        raise BusinessError(409, "no_final", "尚无当前交付图，请先生成或切换到已有版本")
    assets = validate_selection(result_assets(session, order_id), [r.asset_id for r in records])
    return ExportPlan(order_id, order.order_no, [record.id for record in records], assets)


def build_export(storage: Path, plan: ExportPlan) -> ExportFile:
    # 文件名仅来自受控编号/图片 ID，不使用昵称、原文件名或前端路径。
    order_name = re.sub(r"[^A-Za-z0-9_-]", "_", plan.order_no)
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

    if len(plan.assets) != 1:
        raise BusinessError(409, "invalid_final_count", "当前交付图必须恰好一张")
    asset = plan.assets[0]
    filename = f"{order_name}_{asset.id[:8]}.{extensions[asset.mime_type]}"
    return ExportFile(filename, asset.mime_type, verify_input(storage, asset))


def record_export(session: Session, plan: ExportPlan):
    # 组装文件不占写锁；提交导出记录前复验选择，避免交付期间改图导致串版本。
    records = current_selections(session, plan.order_id)
    if [record.id for record in records] != plan.selection_ids:
        raise BusinessError(409, "finals_changed", "最终选择已变化，请刷新后重新下载")
    validate_selection(
        result_assets(session, plan.order_id), [record.asset_id for record in records]
    )
    now = utc_now()
    for record in records:
        record.last_exported_at = now
    logger.info("交付文件已准备 order_id=%s count=%s", plan.order_id, len(records))
