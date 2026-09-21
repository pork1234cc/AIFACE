"""风格示意图提交、下载和受理不明核对入口。"""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.generation import RequestKey
from app.models.orders import GenerationTask, StylePreviewTask
from app.providers import apii as apii_protocol
from app.providers.apii import ApiiProvider, ProviderError
from app.services import style_previews as service
from app.services.orders import BusinessError, write_session
from app.services.styles import load_style

router = APIRouter(prefix="/api/styles", tags=["风格示意图"])


@router.post("/{style_id}/previews", status_code=202)
def generate_preview(
    request: Request, style_id: str, payload: service.PreviewRequest, key: RequestKey
):
    with write_session(request.app.state.engine) as session:
        return service.create_preview(session, style_id, payload, key).model_dump()


@router.post("/{style_id}/previews/{task_id}/resume", status_code=202)
def resume_preview(request: Request, style_id: str, task_id: str):
    with write_session(request.app.state.engine) as session:
        return service.resume_download(session, style_id, task_id).model_dump()


@router.get("/{style_id}/previews/{task_id}/content")
def preview_content(request: Request, style_id: str, task_id: str):
    with Session(request.app.state.engine) as session:
        task = service.preview_task(session, style_id, task_id)
        return FileResponse(
            service.cover_path(request.app.state.settings.storage_path, task),
            media_type=task.mime_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=31536000, immutable",
            },
        )


@router.post("/{style_id}/previews/{task_id}/reconcile")
def reconcile_preview(
    request: Request, style_id: str, task_id: str, payload: service.PreviewReconcile
):
    with Session(request.app.state.engine) as session:
        task = service.preview_task(session, style_id, task_id)
        if task.status != "submission_unknown":
            # 网络中断后重放已完成的核对，不创建新任务。
            if task.reconcile_note == payload.note and (
                (
                    payload.action == "confirm_not_accepted"
                    and task.error_code == "confirmed_not_accepted"
                )
                or (
                    payload.action == "link_remote_task"
                    and task.provider_task_id == payload.provider_task_id
                )
            ):
                return load_style(style_id, session).model_dump()
            raise BusinessError(409, "preview_not_unknown", "只有受理结果不明的任务需要核对")
    if payload.action == "link_remote_task":
        if not payload.provider_task_id:
            raise BusinessError(422, "missing_remote_id", "请填写供应商任务编号")
        provider = ApiiProvider(request.app.state.settings)
        try:
            result = (
                provider.query(payload.provider_task_id, task.request_snapshot_json.get("_api_url"))
                if isinstance(provider, apii_protocol.ApiiProvider)
                else provider.query(payload.provider_task_id)
            )
            if (
                result.get("model") != task.request_snapshot_json["model"]
                or result.get("type") != "edit"
            ):
                raise BusinessError(422, "remote_task_mismatch", "远端任务模型或类型不匹配")
        except ProviderError as exc:
            raise BusinessError(422, exc.code, exc.message) from exc
        finally:
            provider.close()
    elif not payload.confirmed_not_accepted:
        raise BusinessError(422, "confirmation_required", "请先核对供应商记录并确认任务未受理")
    with write_session(request.app.state.engine) as session:
        current = service.preview_task(session, style_id, task_id)
        if current.status != "submission_unknown":
            raise BusinessError(409, "preview_already_reconciled", "任务已核对，请刷新")
        if payload.action == "link_remote_task":
            duplicate = session.scalar(
                select(StylePreviewTask.id).where(
                    StylePreviewTask.provider_task_id == payload.provider_task_id,
                )
            ) or session.scalar(
                select(GenerationTask.id).where(
                    GenerationTask.provider_task_id == payload.provider_task_id,
                )
            )
            if duplicate:
                raise BusinessError(409, "remote_task_in_use", "该远端任务已被关联")
            current.provider_task_id, current.status = payload.provider_task_id, "queued"
            current.next_poll_at = None
            current.error_code = current.error_message = None
        else:
            current.status, current.error_code = "failed", "confirmed_not_accepted"
            current.error_message = "已人工确认未受理，可以重新生成"
        current.reconcile_note = payload.note
        return load_style(style_id, session).model_dump()
