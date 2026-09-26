"""任务快照、状态聚合和本地幂等；远端请求由独立 Worker 执行。"""

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.orders import (
    Asset,
    GenerationAction,
    GenerationBatch,
    GenerationTask,
    OrderDelivery,
    utc_now,
)
from app.schemas.generation import ReconcileRequest, RetryRequest
from app.schemas.orders import InitialInputs, Params
from app.services.assets import MAX_BYTES, content_path
from app.services.orders import BusinessError, asset_data, get_assets, get_order
from app.services.prompts import build_initial_prompt

OPEN_STATUSES = {"pending", "running", "needs_attention"}
ACTIVE_TASKS = {"pending", "submitting", "queued", "running", "downloading"}


def request_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def matches_request(batch: GenerationBatch, payload: dict) -> bool:
    if batch.request_hash == request_hash(payload):
        return True
    # 新增默认字段不应让升级前浏览器保留的原请求发生幂等冲突。
    config = dict(payload["config"])
    defaults = Params().model_dump()
    for field in ("mode", "size", "response_format", "async_mode", "mask", "mask_base_asset_id"):
        if field not in batch.params_snapshot_json and config.get(field) == defaults[field]:
            config.pop(field, None)
    return batch.request_hash == request_hash(payload | {"config": config})


def get_batch(session: Session, batch_id: str) -> GenerationBatch:
    batch = session.get(GenerationBatch, batch_id)
    if batch is None:
        raise BusinessError(404, "batch_not_found", "任务组不存在")
    return batch


def get_task(session: Session, task_id: str) -> GenerationTask:
    task = session.get(GenerationTask, task_id)
    if task is None:
        raise BusinessError(404, "task_not_found", "生成任务不存在")
    return task


def latest_tasks(session: Session, batch_id: str) -> dict[int, GenerationTask]:
    tasks = session.scalars(
        select(GenerationTask)
        .where(GenerationTask.batch_id == batch_id)
        .order_by(GenerationTask.attempt_no)
    )
    return {task.slot_index: task for task in tasks}


def ensure_available(session: Session, order_id: str, except_batch: str | None = None) -> None:
    get_order(session, order_id, editable=True)
    query = select(GenerationBatch.id).where(
        GenerationBatch.order_id == order_id, GenerationBatch.status.in_(OPEN_STATUSES)
    )
    if except_batch:
        query = query.where(GenerationBatch.id != except_batch)
    if session.scalar(query) is not None:
        raise BusinessError(409, "generation_in_progress", "本单仍有未结束任务，请先等待或核对")


def make_task(session: Session, batch: GenerationBatch, slot: int, attempt: int = 1):
    model_settings = Settings()
    task = GenerationTask(
        batch_id=batch.id,
        slot_index=slot,
        attempt_no=attempt,
        model=model_settings.image_model,
        request_snapshot_json={
            "model": model_settings.image_model,
            "_api_url": model_settings.image_api_url,
            "_mode": batch.params_snapshot_json.get("mode", "edit"),
            "prompt": batch.prompt_snapshot,
            **(
                {"aspect_ratio": batch.params_snapshot_json["aspect_ratio"]}
                if batch.params_snapshot_json.get("aspect_ratio")
                else {}
            ),
            **(
                {"size": batch.params_snapshot_json["size"]}
                if batch.params_snapshot_json.get("size")
                else {}
            ),
            **(
                {"mask": batch.params_snapshot_json["mask"]}
                if batch.params_snapshot_json.get("mask")
                else {}
            ),
            "quality": model_settings.image_quality,
            "output_format": batch.params_snapshot_json.get("output_format", "png"),
            "response_format": batch.params_snapshot_json.get("response_format", "url"),
            "async": batch.params_snapshot_json.get("async_mode", True),
            "inputs": batch.input_snapshot_json,
        },
    )
    if attempt > 1:
        previous = session.scalar(
            select(GenerationTask)
            .where(GenerationTask.batch_id == batch.id, GenerationTask.slot_index == slot)
            .order_by(GenerationTask.attempt_no.desc())
            .limit(1)
        )
        if previous is not None:
            task.model = previous.model
            task.request_snapshot_json = dict(previous.request_snapshot_json)
    session.add(task)
    session.flush()
    return task


def verify_input(storage: Path, asset: Asset, expected: dict | None = None) -> bytes:
    try:
        with content_path(storage, asset).open("rb") as source:
            data = source.read(MAX_BYTES + 1)
    except OSError as exc:
        raise BusinessError(422, "input_unreadable", "输入文件不可读，请检查存储") from exc
    expected = expected or {"sha256": asset.sha256, "byte_size": asset.byte_size}
    if len(data) != expected["byte_size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
        raise BusinessError(422, "input_changed", "输入文件与保存记录不一致，请恢复原文件")
    return data


def create_initial(
    session: Session, storage: Path, order_id: str, payload: InitialInputs, key: str
) -> GenerationBatch:
    digest = request_hash(payload.model_dump())
    existing = session.scalar(
        select(GenerationBatch).where(
            GenerationBatch.order_id == order_id,
            GenerationBatch.operation == "initial",
            GenerationBatch.request_key == key,
        )
    )
    if existing:
        if not matches_request(existing, payload.model_dump()):
            raise BusinessError(409, "idempotency_conflict", "同一请求编号不能用于不同内容")
        return existing
    ensure_available(session, order_id)
    assets = get_assets(session, order_id)
    preview = preview_creation(session, storage, order_id, payload, "initial")
    by_id = {a.id: a for a in assets}
    snapshots = []
    for item in preview["inputs"]:
        asset = by_id[item["asset_id"]]
        verify_input(storage, asset)
        snapshots.append(
            item
            | {
                "relative_path": asset.relative_path,
                "mime_type": asset.mime_type,
                "sha256": asset.sha256,
                "byte_size": asset.byte_size,
                "width": asset.width,
                "height": asset.height,
            }
        )
    batch = GenerationBatch(
        order_id=order_id,
        request_key=key,
        request_hash=digest,
        base_asset_id=payload.config.base_asset_id,
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


def preview_creation(
    session: Session,
    storage: Path,
    order_id: str,
    payload: InitialInputs,
    operation: str | None = None,
) -> dict:
    """预览与提交共用底图版本、素材关系及文件完整性检查。"""
    order = get_order(session, order_id, editable=True)
    assets = get_assets(session, order_id)
    if (
        payload.config.size
        and not payload.config.aspect_ratio
        and Settings().image_model == "gpt-image-2.5-sunburst"
    ):
        width, height = map(int, payload.config.size.split("x"))
        if max(width, height) > 3840 or width * height > 3686400:
            raise BusinessError(
                422, "invalid_size", "Sunburst 单边不能超过3840，总像素不能超过3686400"
            )
    if payload.config.mode == "generate":
        if operation == "revision":
            raise BusinessError(422, "invalid_mode", "继续修改需要图片编辑模式")
        return build_initial_prompt(order, assets, payload, session)
    base = next((asset for asset in assets if asset.id == payload.config.base_asset_id), None)
    if base is None:
        raise BusinessError(422, "invalid_base", "请选择本订单的编辑底图")
    if operation == "initial" and base.kind != "input":
        raise BusinessError(422, "invalid_base", "首次生成需要本单上传主照片")
    if operation == "revision" and base.kind != "generated":
        raise BusinessError(422, "invalid_base", "继续修改需要当前交付图")
    if base.kind == "generated":
        task = session.get(GenerationTask, base.generation_task_id)
        current = session.scalar(
            select(OrderDelivery.asset_id).where(
                OrderDelivery.order_id == order_id,
                OrderDelivery.revoked_at.is_(None),
            )
        )
        if base.review_status == "discarded" or task is None or task.status != "succeeded":
            raise BusinessError(409, "base_unavailable", "底图必须已成功保存且未作废")
        if current != base.id:
            raise BusinessError(409, "base_changed", "底图已不是当前交付图，请刷新并重新选择")
    preview = build_initial_prompt(order, assets, payload, session)
    by_id = {asset.id: asset for asset in assets}
    for item in preview["inputs"]:
        verify_input(storage, by_id[item["asset_id"]])
    return preview


def aggregate(session: Session, batch: GenerationBatch) -> None:
    session.flush()
    statuses = [task.status for task in latest_tasks(session, batch.id).values()]
    if "submission_unknown" in statuses:
        batch.status = "needs_attention"
    elif any(status in ACTIVE_TASKS for status in statuses):
        batch.status = "pending" if all(s == "pending" for s in statuses) else "running"
    elif statuses.count("succeeded") == batch.target_count:
        batch.status = "succeeded"
    else:
        batch.status = "partial_failed" if "succeeded" in statuses else "failed"
    batch.finished_at = None if batch.status in OPEN_STATUSES else utc_now()
    order = get_order(session, batch.order_id)
    if order.status not in {"completed", "closed"}:
        if batch.status == "succeeded":
            next_status = "review"
        elif batch.status in OPEN_STATUSES:
            next_status = "modifying" if batch.operation == "revision" else "generating"
        else:
            next_status = "review" if batch.operation == "revision" else "draft"
        if order.status != next_status:
            order.status, order.updated_at = next_status, utc_now()


def action_replay(session: Session, scope: str, key: str, payload: dict):
    record = session.scalar(
        select(GenerationAction).where(
            GenerationAction.scope == scope, GenerationAction.request_key == key
        )
    )
    if record and record.request_hash != request_hash(payload):
        raise BusinessError(409, "idempotency_conflict", "同一请求编号不能用于不同内容")
    return record


def record_action(session: Session, scope: str, key: str, payload: dict, batch_id: str):
    session.add(
        GenerationAction(
            scope=scope, request_key=key, request_hash=request_hash(payload), batch_id=batch_id
        )
    )


def retry_batch(session: Session, batch_id: str, payload: RetryRequest, key: str):
    batch = get_batch(session, batch_id)
    scope = f"retry:{batch_id}"
    if action_replay(session, scope, key, payload.model_dump()):
        return batch
    ensure_available(session, batch.order_id, batch.id)
    current = latest_tasks(session, batch.id)
    if len(set(payload.slot_indices)) != len(payload.slot_indices):
        raise BusinessError(422, "duplicate_slot", "候选位置不能重复")
    for slot in payload.slot_indices:
        task = current.get(slot)
        if task is None or task.status != "failed":
            raise BusinessError(409, "slot_not_failed", "只能补生成明确失败的位置")
    for slot in payload.slot_indices:
        task = current[slot]
        if task.failure_stage in {"download", "persist", "protocol"} and (
            task.provider_task_id or task.result_metadata_json
        ):
            task.status = "downloading" if task.result_metadata_json else "queued"
            task.error_code = task.error_message = task.failure_stage = task.finished_at = None
            task.next_poll_at = None
        else:
            make_task(session, batch, slot, task.attempt_no + 1)
    record_action(session, scope, key, payload.model_dump(), batch.id)
    aggregate(session, batch)
    return batch


def reconcile_task(
    session: Session,
    task_id: str,
    payload: ReconcileRequest,
    key: str,
    remote_verified: bool = False,
):
    task = get_task(session, task_id)
    batch = get_batch(session, task.batch_id)
    scope = f"reconcile:{task_id}"
    if action_replay(session, scope, key, payload.model_dump()):
        return batch
    ensure_available(session, batch.order_id, batch.id)
    if task.status != "submission_unknown":
        raise BusinessError(409, "task_not_unknown", "仅提交结果不明的任务可人工核对")
    if payload.action == "link_remote_task":
        if not payload.provider_task_id or not remote_verified:
            raise BusinessError(422, "remote_not_verified", "请先提供并核对有效远端任务编号")
        task.provider_task_id = payload.provider_task_id
        task.status = "queued"
    elif payload.action == "resubmit_with_risk":
        if not payload.acknowledge_possible_duplicate_charge:
            raise BusinessError(422, "risk_not_acknowledged", "重新生成须明确接受可能重复计费")
        task.status = "superseded_unknown"
        task.finished_at = utc_now()
        make_task(session, batch, task.slot_index, task.attempt_no + 1)
    else:
        task.status, task.failure_stage, task.finished_at = "failed", "submit", utc_now()
    task.resolution_json = payload.model_dump() | {"resolved_at": utc_now()}
    task.error_code = task.error_message = None
    record_action(session, scope, key, payload.model_dump(), batch.id)
    aggregate(session, batch)
    return batch


def task_data(task: GenerationTask) -> dict:
    return {
        key: getattr(task, key)
        for key in (
            "id",
            "batch_id",
            "slot_index",
            "attempt_no",
            "status",
            "provider",
            "model",
            "provider_task_id",
            "error_code",
            "error_message",
            "failure_stage",
            "next_poll_at",
            "submitted_at",
            "finished_at",
            "cost_amount",
            "cost_currency",
            "cost_source",
        )
    }


def batch_data(session: Session, batch: GenerationBatch) -> dict:
    tasks = list(
        session.scalars(
            select(GenerationTask)
            .where(GenerationTask.batch_id == batch.id)
            .order_by(GenerationTask.slot_index, GenerationTask.attempt_no)
        )
    )
    outputs = list(
        session.scalars(select(Asset).where(Asset.generation_task_id.in_([t.id for t in tasks])))
    )
    return {
        "batch_id": batch.id,
        "order_id": batch.order_id,
        "operation": batch.operation,
        "base_asset_id": batch.base_asset_id,
        "revision_instruction": batch.revision_instruction,
        "style_version": batch.style_snapshot_json.get("version"),
        "config": batch.params_snapshot_json,
        "prompt": batch.prompt_snapshot,
        "inputs": [
            {"asset_id": item["asset_id"], "role": item["role"]}
            for item in batch.input_snapshot_json
        ],
        "target_count": batch.target_count,
        "status": batch.status,
        "created_at": batch.created_at,
        "finished_at": batch.finished_at,
        "tasks": [task_data(t) for t in tasks],
        "outputs": [asset_data(a) | {"generation_task_id": a.generation_task_id} for a in outputs],
    }
