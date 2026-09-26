"""动态元素识别、外部 Codex 结果导入与选区修正。"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.models.orders import Asset
from app.schemas.orders import Params
from app.services import element_jobs, orders
from app.services.elements import Analysis
from app.services.generation import verify_input

router = APIRouter(prefix="/api/orders/{order_id}/images/{asset_id}/elements", tags=["元素"])


class ImportAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    analysis: Analysis


class CorrectionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=1000)
    label: int = Field(ge=0, le=1, strict=True)


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{12}$")]
    points: list[CorrectionPoint] = Field(min_length=1, max_length=16)


def context(request: Request, order_id: str, asset_id: str, *, write: bool = False):
    storage = request.app.state.settings.storage_path
    with Session(request.app.state.engine) as session:
        order = orders.get_order(session, order_id)
        asset = session.get(Asset, asset_id)
        if asset is None or asset.order_id != order_id:
            raise orders.BusinessError(404, "image_not_found", "图片不存在")
        if Params.model_validate(order.params_json).base_asset_id != asset_id or (
            asset.kind == "input" and (not asset.is_active_input or asset.input_role != "main")
        ):
            raise orders.BusinessError(409, "region_base_changed", "底图已变化，请刷新后识别")
        if write and order.status in {"completed", "closed"}:
            raise orders.BusinessError(409, "order_read_only", "订单已归档")
        data = verify_input(storage, asset)
    return element_jobs.location(storage, order_id, asset_id), data


@router.get("")
def get_elements(request: Request, order_id: str, asset_id: str):
    directory, data = context(request, order_id, asset_id)
    return {
        "asset_id": asset_id,
        **element_jobs.public_result(element_jobs.status(directory, data)),
    }


@router.post("", status_code=202)
def analyze_elements(request: Request, order_id: str, asset_id: str):
    directory, data = context(request, order_id, asset_id, write=True)
    return {"asset_id": asset_id, **element_jobs.start(directory, data)}


@router.post("/import", status_code=202)
def import_elements(request: Request, order_id: str, asset_id: str, payload: ImportAnalysis):
    directory, data = context(request, order_id, asset_id, write=True)
    if hashlib.sha256(data).hexdigest() != payload.image_sha256:
        raise orders.BusinessError(409, "element_image_mismatch", "分析结果与当前图片不匹配")
    try:
        result = element_jobs.start(directory, data, payload.analysis.model_dump())
    except ValueError as exc:
        raise orders.BusinessError(422, "invalid_elements", "对象层级或坐标无效") from exc
    return {"asset_id": asset_id, **result}


@router.post("/{region_id}/refine")
def refine_element(
    request: Request,
    order_id: str,
    asset_id: str,
    region_id: str,
    payload: Correction,
):
    directory, data = context(request, order_id, asset_id, write=True)
    result = element_jobs.refine(
        directory, data, region_id, payload.version, [[p.x, p.y, p.label] for p in payload.points]
    )
    return {"asset_id": asset_id, **result}
