"""阶段 2 本地订单、素材、风格接口。"""

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
from app.services import orders
from app.services.prompts import (
    build_initial_prompt,
    readiness_errors,
    refresh_readiness,
    validate_sources,
)
from app.services.styles import load_style

router = APIRouter(prefix="/api")


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
        return build_initial_prompt(
            orders.get_order(session, order_id),
            orders.get_assets(session, order_id),
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
def list_styles():
    return {"items": [load_style().model_dump()]}


@router.get("/styles/{style_id}", tags=["风格"])
def get_style(style_id: str):
    return load_style(style_id).model_dump()
