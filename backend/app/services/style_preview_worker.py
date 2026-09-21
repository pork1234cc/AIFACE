"""由现有单进程 Worker 驱动风格示意图，不在 HTTP 请求中阻塞生成。"""

import hashlib
import io
import os

from sqlalchemy import or_, select

from app.models.orders import CustomStyle, StylePreviewTask, new_id, utc_now
from app.providers.apii import ProviderError
from app.services import style_previews
from app.services.assets import decode_upload
from app.services.orders import BusinessError, write_session


def recover_previews(session):
    for task in session.scalars(
        select(StylePreviewTask).where(
            StylePreviewTask.status == "submitting",
        )
    ):
        if task.provider_task_id:
            task.status = "queued"
        else:
            task.status = "submission_unknown"
            task.error_code = "worker_interrupted"
            task.error_message = "提交期间服务中断，受理结果不明，请核对供应商任务"


def step_preview(worker) -> bool:
    with write_session(worker.engine) as session:
        task = session.scalar(
            select(StylePreviewTask)
            .where(
                StylePreviewTask.status.in_({"pending", "queued", "running", "downloading"}),
                or_(
                    StylePreviewTask.next_poll_at.is_(None),
                    StylePreviewTask.next_poll_at <= utc_now(),
                ),
            )
            .order_by(StylePreviewTask.next_poll_at, StylePreviewTask.created_at)
            .limit(1)
        )
        if task is None:
            return False
        mode = task.status
        if mode == "pending":
            task.status = "submitting"
    try:
        if mode == "pending":
            data = style_previews.REFERENCE_IMAGE.read_bytes()
            if hashlib.sha256(data).hexdigest() != task.reference_sha256:
                raise BusinessError(422, "preview_reference_changed", "示例底图已变更，请重新生成")
            result = worker.provider.submit(
                task.request_snapshot_json, [data], f"preview-{task.id}"
            )
            with write_session(worker.engine) as session:
                current = session.get(StylePreviewTask, task.id)
                current.provider_task_id = result["task_id"]
                current.status, current.next_poll_at = "queued", worker._next_poll()
        elif mode == "downloading":
            download_preview(worker, task)
        else:
            result = worker.query_provider(task.provider_task_id, task.request_snapshot_json)
            with write_session(worker.engine) as session:
                current = session.get(StylePreviewTask, task.id)
                current.error_code = current.error_message = None
                current.poll_failures = 0
                if result["status"] == "succeeded":
                    current.download_url = result["url"]
                    current.status, current.next_poll_at = "downloading", None
                elif result["status"] == "failed":
                    current.status, current.error_code = "failed", "remote_failed"
                    current.error_message = "供应商明确返回生成失败，可重新生成"
                else:
                    current.status, current.next_poll_at = result["status"], worker._next_poll()
    except (ProviderError, BusinessError, OSError) as exc:
        with write_session(worker.engine) as session:
            current = session.get(StylePreviewTask, task.id)
            current.error_code = getattr(exc, "code", "storage_error")
            current.error_message = getattr(exc, "message", "本地图片读写失败，请检查存储后重试")
            if mode in {"queued", "running"}:
                current.poll_failures += 1
                current.next_poll_at = worker._next_poll(current.poll_failures)
            else:
                current.status = (
                    "submission_unknown" if getattr(exc, "uncertain", False) else "failed"
                )
    return True


def download_preview(worker, task):
    data = worker.provider.download(task.download_url)
    decoded, extension, mime, _, _ = decode_upload(io.BytesIO(data))
    relative = f"style-previews/{task.style_id}/{task.id}.{extension}"
    root = worker.settings.storage_path.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise BusinessError(422, "invalid_preview_path", "示意图存储路径无效")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(decoded).digest():
            raise BusinessError(
                409, "preview_output_conflict", "已有示意图文件内容不符，请核对存储"
            )
    else:
        temporary = target.with_suffix(f".{new_id()}.part")
        with temporary.open("xb") as output:
            output.write(decoded)
            output.flush()
            os.fsync(output.fileno())
        temporary.rename(target)
    with write_session(worker.engine) as session:
        current = session.get(StylePreviewTask, task.id)
        row = session.get(CustomStyle, task.style_id)
        current.status, current.relative_path, current.mime_type = "succeeded", relative, mime
        current.download_url = None
        current.error_code = current.error_message = None
        # 旧文件不删除；任务成功才更新封面，提示词期间改变时标记封面过期。
        if row.preview_task_id == task.id:
            row.cover_task_id, row.cover_version = task.id, task.style_version
