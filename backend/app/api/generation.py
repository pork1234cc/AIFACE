"""生成、任务查询与人工恢复接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orders import GenerationBatch
from app.providers.apii import ApiiProvider, ProviderError
from app.schemas.generation import ReconcileRequest, RetryRequest, ReviewRequest, RevisionRequest
from app.schemas.orders import InitialInputs
from app.services import generation as service
from app.services import revisions
from app.services.orders import BusinessError, asset_data, get_order, order_data, write_session

router = APIRouter(prefix="/api", tags=["生成任务"])
RequestKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
]


@router.post("/orders/{order_id}/generate", status_code=202)
def generate(request: Request, order_id: str, payload: InitialInputs, key: RequestKey):
    with write_session(request.app.state.engine) as session:
        batch = service.create_initial(
            session, request.app.state.settings.storage_path, order_id, payload, key
        )
        return service.batch_data(session, batch)


@router.post("/orders/{order_id}/revise", status_code=202)
def revise(request: Request, order_id: str, payload: RevisionRequest, key: RequestKey):
    with write_session(request.app.state.engine) as session:
        batch = revisions.create_revision(
            session, request.app.state.settings.storage_path, order_id, payload, key
        )
        return service.batch_data(session, batch)


@router.patch("/images/{asset_id}/review")
def review(request: Request, asset_id: str, payload: ReviewRequest):
    with write_session(request.app.state.engine) as session:
        return asset_data(revisions.review_result(session, asset_id, payload))


@router.post("/orders/{order_id}/request-revision")
def request_revision(request: Request, order_id: str):
    with write_session(request.app.state.engine) as session:
        return order_data(revisions.request_revision(session, order_id))


@router.get("/orders/{order_id}/generation-stats")
def generation_stats(request: Request, order_id: str):
    with Session(request.app.state.engine) as session:
        get_order(session, order_id)
        return revisions.revision_stats(session, order_id)


@router.get("/orders/{order_id}/batches")
def batches(
    request: Request,
    order_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    with Session(request.app.state.engine) as session:
        get_order(session, order_id)
        query = select(GenerationBatch).where(GenerationBatch.order_id == order_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(GenerationBatch.created_at.desc(), GenerationBatch.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        # 列表只返回摘要，详细任务和图片按需查询，避免逐组 N+1。
        return {
            "items": [
                {
                    "batch_id": b.id,
                    "operation": b.operation,
                    "status": b.status,
                    "target_count": b.target_count,
                    "created_at": b.created_at,
                    "base_asset_id": b.base_asset_id,
                    "revision_instruction": b.revision_instruction,
                }
                for b in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get("/batches/{batch_id}")
def batch_detail(request: Request, batch_id: str):
    with Session(request.app.state.engine) as session:
        return service.batch_data(session, service.get_batch(session, batch_id))


@router.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: str):
    with Session(request.app.state.engine) as session:
        return service.task_data(service.get_task(session, task_id))


@router.post("/batches/{batch_id}/retry", status_code=202)
def retry(request: Request, batch_id: str, payload: RetryRequest, key: RequestKey):
    with write_session(request.app.state.engine) as session:
        return service.batch_data(session, service.retry_batch(session, batch_id, payload, key))


@router.post("/tasks/{task_id}/reconcile", status_code=202)
def reconcile(request: Request, task_id: str, payload: ReconcileRequest, key: RequestKey):
    with Session(request.app.state.engine) as session:
        task = service.get_task(session, task_id)
        record = service.action_replay(session, f"reconcile:{task_id}", key, payload.model_dump())
        if record:
            return service.batch_data(session, service.get_batch(session, record.batch_id))
        get_order(session, service.get_batch(session, task.batch_id).order_id, editable=True)
        if task.status != "submission_unknown":
            raise BusinessError(409, "task_not_unknown", "仅提交结果不明的任务可人工核对")
    verified = False
    if payload.action == "link_remote_task":
        if not payload.provider_task_id:
            raise BusinessError(422, "missing_remote_id", "请填写供应商任务编号")
        provider = ApiiProvider(request.app.state.settings)
        try:
            result = provider.query(payload.provider_task_id)
            verified = result.get("model") == task.model and result.get("type") == "edit"
            if not verified:
                raise BusinessError(422, "remote_task_mismatch", "远端任务模型或类型不匹配")
        except ProviderError as exc:
            raise BusinessError(422, exc.code, "远端核对未通过；" + exc.message) from exc
        finally:
            provider.close()
    with write_session(request.app.state.engine) as session:
        batch = service.reconcile_task(session, task_id, payload, key, verified)
        return service.batch_data(session, batch)
