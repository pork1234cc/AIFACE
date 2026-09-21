"""本机模型设置 API，沿用现有 Apii 请求协议。"""

import os

from fastapi import APIRouter, Request

from app.config import Settings
from app.services.model_settings import FIELDS, ModelSettingsRequest, public_settings, save_settings
from app.services.orders import BusinessError

router = APIRouter(prefix="/api/model-settings", tags=["模型设置"])


@router.get("")
def get_model_settings(request: Request):
    return public_settings(Settings(_env_file=request.app.state.settings_file))


@router.put("")
def put_model_settings(request: Request, payload: ModelSettingsRequest):
    if any(name in os.environ for name in FIELDS):
        raise BusinessError(
            409, "model_settings_overridden", "模型设置由进程环境变量管理，请修改启动环境"
        )
    try:
        settings = save_settings(request.app.state.settings_file, payload)
    except ValueError as exc:
        raise BusinessError(
            422, "invalid_model_settings", "接口 URL、模型、质量或 API Key 格式不正确"
        ) from exc
    request.app.state.settings.image_api_url = settings.image_api_url
    request.app.state.settings.image_model = settings.image_model
    request.app.state.settings.image_quality = settings.image_quality
    request.app.state.settings.image_api = settings.image_api
    return public_settings(settings)
