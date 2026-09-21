"""阶段 2 本地订单、素材、风格接口。"""

import logging
import shutil
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.orders import Asset
from app.schemas.orders import (
    ActivePatch,
    InitialInputs,
    OrderCreate,
    OrderPatch,
    OrderStatus,
    Params,
    Role,
    RolePatch,
)
from app.services import assets as asset_service
from app.services import input_slots, orders
from app.services import styles as style_service
from app.services.generation import preview_creation
from app.services.prompts import (
    readiness_errors,
    refresh_readiness,
    validate_sources,
)
from app.services.styles import CustomStyleCreate, CustomStyleUpdate, load_style

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def detail(session: Session, order_id: str) -> dict:
    order = orders.get_order(session, order_id)
    assets = orders.get_assets(session, order_id)
    errors = readiness_errors(Params.model_validate(order.params_json), assets)
    return orders.order_data(order) | {
        "assets": [orders.asset_data(asset) for asset in assets],
        "readiness": {"ready": not errors, "errors": errors},
    }


@router.post("/orders", status_code=201, tags=["订单"])
def create_order(request: Request, payload: OrderCreate):
    with orders.write_session(request.app.state.engine) as session:
        order = orders.create_order(session, payload)
        return detail(session, order.id)


@router.get("/orders", tags=["订单"])
def list_orders(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: OrderStatus | None = None,
    q: Annotated[str, Query(max_length=100)] = "",
):
    with Session(request.app.state.engine) as session:
        return orders.list_orders(session, page, page_size, status, q)


@router.get("/orders/{order_id}", tags=["订单"])
def get_order(request: Request, order_id: str):
    with Session(request.app.state.engine) as session:
        return detail(session, order_id)


@router.delete("/orders/{order_id}", tags=["订单"])
def delete_order(request: Request, order_id: str):
    storage = request.app.state.settings.storage_path.resolve()
    orders_root = (storage / "orders").resolve()
    order_dir = storage / "orders" / order_id
    if (
        not orders_root.is_relative_to(storage)
        or order_dir.is_symlink()
        or order_dir.is_junction()
        or order_dir.resolve().parent != orders_root
    ):
        raise orders.BusinessError(409, "unsafe_order_path", "订单存储路径异常，无法安全删除")
    with orders.write_session(request.app.state.engine) as session:
        orders.delete_order(session, order_id)
    files_removed = True
    if order_dir.exists():
        try:
            shutil.rmtree(order_dir)
        except OSError:
            logger.exception("删除订单文件失败：%s", order_id)
            files_removed = False
    return {"deleted": True, "files_removed": files_removed}


@router.patch("/orders/{order_id}", tags=["订单"])
def patch_order(request: Request, order_id: str, payload: OrderPatch):
    with orders.write_session(request.app.state.engine) as session:
        orders.update_order(session, order_id, payload)
        return detail(session, order_id)


@router.patch("/orders/{order_id}/params", tags=["订单"])
def patch_params(request: Request, order_id: str, payload: Params):
    with orders.write_session(request.app.state.engine) as session:
        order = orders.get_order(session, order_id, editable=True)
        params = Params.model_validate(order.params_json | payload.model_dump(exclude_unset=True))
        if params.style_id:
            load_style(params.style_id, session)
        assets = orders.get_assets(session, order_id)
        validate_sources(params, assets)
        order.params_json = params.model_dump()
        refresh_readiness(order, assets)
        return detail(session, order_id)


@router.post("/orders/{order_id}/ready", tags=["订单"])
def ready_order(request: Request, order_id: str):
    with orders.write_session(request.app.state.engine) as session:
        order = orders.get_order(session, order_id, editable=True)
        errors = refresh_readiness(order, orders.get_assets(session, order_id))
        if errors:
            raise orders.BusinessError(422, "order_not_ready", "；".join(errors))
        return detail(session, order_id)


@router.post("/orders/{order_id}/prompt-preview", tags=["订单"])
def preview_prompt(request: Request, order_id: str, payload: InitialInputs):
    # 只读预检；阶段 3 创建快照时仍须在同一写事务内重新校验。
    with Session(request.app.state.engine) as session:
        return preview_creation(
            session,
            request.app.state.settings.storage_path,
            order_id,
            payload,
        )


@router.post("/orders/{order_id}/images", status_code=201, tags=["素材"])
def upload_image(
    request: Request,
    order_id: str,
    role: Annotated[Role, Form()],
    file: Annotated[UploadFile, File()],
):
    decoded = asset_service.decode_upload(file.file)
    with orders.write_session(request.app.state.engine) as session:
        asset = asset_service.add_asset(
            session,
            request.app.state.settings.storage_path,
            order_id,
            role,
            file.filename or "",
            decoded,
        )
        return orders.asset_data(asset)


@router.post("/orders/{order_id}/image-slots/{slot}", tags=["素材"])
def upload_slot(request: Request, order_id: str, slot: str, file: Annotated[UploadFile, File()]):
    decoded = asset_service.decode_upload(file.file)
    with orders.write_session(request.app.state.engine) as session:
        input_slots.update_slot(
            session,
            request.app.state.settings.storage_path,
            order_id,
            slot,
            file.filename or "",
            decoded,
        )
        return detail(session, order_id)


@router.post("/orders/{order_id}/image-slots/{slot}/clear", tags=["素材"])
def clear_slot(request: Request, order_id: str, slot: str):
    with orders.write_session(request.app.state.engine) as session:
        input_slots.update_slot(session, request.app.state.settings.storage_path, order_id, slot)
        return detail(session, order_id)


@router.patch("/orders/{order_id}/images/{asset_id}/role", tags=["素材"])
def patch_role(request: Request, order_id: str, asset_id: str, payload: RolePatch):
    with orders.write_session(request.app.state.engine) as session:
        asset_service.set_role(session, order_id, asset_id, payload.role)
        return detail(session, order_id)


@router.patch("/orders/{order_id}/images/{asset_id}/active", tags=["素材"])
def patch_active(request: Request, order_id: str, asset_id: str, payload: ActivePatch):
    with orders.write_session(request.app.state.engine) as session:
        asset_service.set_active(session, order_id, asset_id, payload.active)
        return detail(session, order_id)


@router.get("/images/{asset_id}/content", tags=["素材"])
def image_content(request: Request, asset_id: str):
    with Session(request.app.state.engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            raise orders.BusinessError(404, "image_not_found", "图片不存在")
        path = asset_service.content_path(request.app.state.settings.storage_path, asset)
        return FileResponse(
            path,
            media_type=asset.mime_type,
            filename=asset.original_name,
            content_disposition_type="inline",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"},
        )


@router.get("/styles", tags=["风格"])
def list_styles(request: Request):
    with Session(request.app.state.engine) as session:
        return {"items": [style.model_dump() for style in style_service.list_styles(session)]}


@router.post("/styles", status_code=201, tags=["风格"])
def create_style(request: Request, payload: CustomStyleCreate):
    with orders.write_session(request.app.state.engine) as session:
        return style_service.create_style(session, payload).model_dump()


@router.put("/styles/{style_id}", tags=["风格"])
def update_style(request: Request, style_id: str, payload: CustomStyleUpdate):
    with orders.write_session(request.app.state.engine) as session:
        return style_service.update_style(session, style_id, payload).model_dump()


@router.get("/styles/{style_id}", tags=["风格"])
def get_style(request: Request, style_id: str):
    with Session(request.app.state.engine) as session:
        return load_style(style_id, session).model_dump()
