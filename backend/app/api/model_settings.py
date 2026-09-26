"""本机模型设置 API，沿用现有 Apii 请求协议。"""

import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.services import codex_runtime
from app.services.model_settings import FIELDS, ModelSettingsRequest, public_settings, save_settings
from app.services.orders import BusinessError

router = APIRouter(prefix="/api/model-settings", tags=["模型设置"])


class CodexPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=4096)


@router.get("/codex")
def get_codex_settings():
    return codex_runtime.status()


@router.put("/codex")
def put_codex_settings(payload: CodexPathRequest):
    return codex_runtime.save_path(payload.path)


@router.post("/codex/detect")
def detect_codex(payload: CodexPathRequest):
    return codex_runtime.status(payload.path.strip())


@router.post("/codex/browse")
def browse_codex(request: Request):
    # 系统选择窗口属于服务所在电脑，仅允许本机页面发起。
    local = {"127.0.0.1", "::1", "localhost"}
    origin = urlsplit(request.headers.get("origin", "")).hostname
    forwarded = request.headers.get("x-forwarded-for", "")
    if (
        not request.client
        or request.client.host not in local
        or origin not in local
        or any(part.strip() not in local for part in forwarded.split(",") if part.strip())
    ):
        raise BusinessError(
            403, "codex_picker_local_only", "请在运行 AIFACE 的电脑上打开本机网址浏览文件"
        )
    return {"path": codex_runtime.choose_path()}


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
