"""风格封面任务：独立队列、固定输入、幂等提交和受控图片访问。"""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, Settings
from app.models.orders import CustomStyle, StylePreviewTask
from app.services.orders import BusinessError
from app.services.styles import load_style

REFERENCE_IMAGE = PROJECT_ROOT / "styles/preview/base-portrait.png"
ACTIVE = {"pending", "submitting", "queued", "running", "downloading", "submission_unknown"}


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)


class PreviewReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["link_remote_task", "confirm_not_accepted"]
    provider_task_id: (
        Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")] | None
    ) = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]
    confirmed_not_accepted: bool = False


def custom_style(session: Session, style_id: str) -> CustomStyle:
    if style_id == "q_crayon_001":
        raise BusinessError(403, "builtin_style_readonly", "内置风格不支持重新生成示意图")
    row = session.get(CustomStyle, style_id)
    if row is None:
        raise BusinessError(404, "style_not_found", "风格不存在")
    return row


def preview_task(session: Session, style_id: str, task_id: str) -> StylePreviewTask:
    task = session.get(StylePreviewTask, task_id)
    if task is None or task.style_id != style_id:
        raise BusinessError(404, "preview_not_found", "示意图任务不存在")
    return task


def create_preview(session: Session, style_id: str, payload: PreviewRequest, key: str):
    row = custom_style(session, style_id)
    existing = session.scalar(
        select(StylePreviewTask).where(
            StylePreviewTask.style_id == style_id,
            StylePreviewTask.idempotency_key == key,
        )
    )
    if existing:
        if existing.style_version != payload.expected_version:
            raise BusinessError(409, "idempotency_conflict", "同一请求编号对应不同风格版本")
        return load_style(style_id, session)
    task = session.get(StylePreviewTask, row.preview_task_id) if row.preview_task_id else None
    if task and task.status in ACTIVE:
        raise BusinessError(409, "preview_in_progress", "该风格仍有未结束或待核对的示意图任务")
    if row.version != payload.expected_version:
        raise BusinessError(409, "style_version_conflict", "风格已更新，请刷新后再生成示意图")
    if task and task.status == "failed" and task.download_url:
        raise BusinessError(409, "preview_download_pending", "请先恢复已有结果下载，无需再次生成")
    try:
        reference = REFERENCE_IMAGE.read_bytes()
    except OSError as exc:
        raise BusinessError(
            422, "preview_reference_missing", "统一示例底图不可读，请检查安装文件"
        ) from exc
    style = load_style(style_id, session)
    prompt = "\n".join(
        [
            "图片 1 是统一风格示例底图。只改变绘画表现方式。",
            "保留人物身份、姿态、服装、背景和构图，不添加文字、水印或其他元素。",
            *style.prompt_template.model_dump().values(),
            "输出一张 1:1 正方形风格示意图。",
        ]
    )
    model_settings = Settings()
    task = StylePreviewTask(
        style_id=style_id,
        style_version=row.version,
        idempotency_key=key,
        reference_sha256=hashlib.sha256(reference).hexdigest(),
        request_snapshot_json={
            "model": model_settings.image_model,
            "_api_url": model_settings.image_api_url,
            "prompt": prompt,
            "aspect_ratio": "1:1",
            "quality": model_settings.image_quality,
            "output_format": "png",
            "response_format": "url",
            "async": True,
        },
    )
    session.add(task)
    session.flush()
    row.preview_task_id = task.id
    return load_style(style_id, session)


def resume_download(session: Session, style_id: str, task_id: str):
    row = custom_style(session, style_id)
    task = preview_task(session, style_id, task_id)
    if row.preview_task_id != task.id:
        raise BusinessError(409, "preview_not_latest", "只能恢复当前示意图任务")
    if task.status in {"downloading", "succeeded"}:
        return load_style(style_id, session)
    if task.status != "failed" or not task.download_url:
        raise BusinessError(409, "preview_not_downloadable", "该任务不能恢复下载")
    task.status, task.next_poll_at = "downloading", None
    task.error_code = task.error_message = None
    return load_style(style_id, session)


def cover_path(storage: Path, task: StylePreviewTask) -> Path:
    if task.status != "succeeded" or not task.relative_path:
        raise BusinessError(404, "preview_not_ready", "示意图尚未生成")
    root = storage.resolve()
    target = (root / task.relative_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise BusinessError(404, "preview_file_missing", "示意图文件不存在")
    return target
