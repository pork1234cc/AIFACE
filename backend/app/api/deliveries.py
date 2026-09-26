"""单张交付图、版本切换与订单完成/关闭。"""

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.orders import detail
from app.schemas.deliveries import FinalsRequest
from app.services import deliveries
from app.services.generation import ensure_available
from app.services.orders import write_session

router = APIRouter(prefix="/api/orders", tags=["交付"])


@router.get("/{order_id}/finals")
def finals(request: Request, order_id: str):
    with Session(request.app.state.engine) as session:
        # sqlite3 默认不会为 SELECT 开启数据库事务；显式固定读取快照。
        # WAL 下 Worker 可以继续写入，响应内的版本、交付和任务状态保持一致。
        session.execute(text("BEGIN"))
        return deliveries.finals_data(session, order_id)


@router.put("/{order_id}/finals")
def set_finals(request: Request, order_id: str, payload: FinalsRequest):
    with write_session(request.app.state.engine) as session:
        ensure_available(session, order_id)
        deliveries.set_finals(session, request.app.state.settings.storage_path, order_id, payload)
        return deliveries.finals_data(session, order_id)


@router.get("/{order_id}/delivery")
def download(request: Request, order_id: str):
    with Session(request.app.state.engine) as session:
        plan = deliveries.plan_export(session, order_id)
    file = deliveries.build_export(request.app.state.settings.storage_path, plan)
    with write_session(request.app.state.engine) as session:
        deliveries.record_export(session, plan)
    return Response(
        file.content,
        media_type=file.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{order_id}/complete")
def complete(request: Request, order_id: str):
    with write_session(request.app.state.engine) as session:
        deliveries.finish_order(
            session, request.app.state.settings.storage_path, order_id, "completed"
        )
        return detail(session, order_id)


@router.post("/{order_id}/close")
def close(request: Request, order_id: str):
    with write_session(request.app.state.engine) as session:
        deliveries.finish_order(
            session, request.app.state.settings.storage_path, order_id, "closed"
        )
        return detail(session, order_id)
