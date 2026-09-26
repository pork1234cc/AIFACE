"""软件授权接口；同步客户端由 FastAPI 在线程池中调用。"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, SecretStr

router = APIRouter(prefix="/api/license", tags=["软件授权"])


class ActivationRequest(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=256)


@router.get("/status")
def status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.license_runtime.status()


@router.post("/activate")
def activate(payload: ActivationRequest, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    code = payload.code.get_secret_value().strip()
    if not code:
        response.status_code = 422
        return {"authorized": False, "message": "请输入卡密"}
    result = request.app.state.license_runtime.activate(code)
    if not result["authorized"]:
        response.status_code = 403
    return result


@router.post("/verify")
def verify(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    result = request.app.state.license_runtime.verify()
    if not result["authorized"]:
        response.status_code = 403
    return result
