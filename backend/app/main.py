"""基础应用入口，统一错误响应并提供数据库就绪检查。"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.api.deliveries import router as deliveries_router
from app.api.elements import router as elements_router
from app.api.generation import router as generation_router
from app.api.license import router as license_router
from app.api.model_settings import router as model_settings_router
from app.api.orders import router as orders_router
from app.api.style_previews import router as style_previews_router
from app.config import PROJECT_ROOT, SETTINGS_FILE, Settings
from app.db import create_db_engine
from app.services.licensing import make_license_runtime
from app.services.orders import BusinessError

logger = logging.getLogger(__name__)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


def create_app(settings: Settings | None = None, *, license_runtime=None) -> FastAPI:
    config = settings if settings is not None else Settings()
    runtime = license_runtime if license_runtime is not None else make_license_runtime()

    async def periodic_license_check():
        while True:
            await asyncio.sleep(60)
            await run_in_threadpool(runtime.poll)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_db_engine(config)
        application.state.engine = engine
        application.state.settings = config
        application.state.license_runtime = runtime
        application.state.settings_file = SETTINGS_FILE
        migration_config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
        application.state.schema_head = ScriptDirectory.from_config(
            migration_config
        ).get_current_head()
        license_task = asyncio.create_task(periodic_license_check())
        try:
            yield
        finally:
            license_task.cancel()
            with suppress(asyncio.CancelledError):
                await license_task
            engine.dispose()

    application = FastAPI(
        title="AIFACE 工作台 API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    application.include_router(orders_router)
    application.include_router(elements_router)
    application.include_router(style_previews_router)
    application.include_router(generation_router)
    application.include_router(deliveries_router)
    application.include_router(model_settings_router)
    application.include_router(license_router)

    @application.exception_handler(BusinessError)
    async def business_error(request: Request, exc: BusinessError):
        return error_response(request, exc.status, exc.code, exc.message)

    @application.exception_handler(IntegrityError)
    async def integrity_error(request: Request, _exc: IntegrityError):
        return error_response(request, 409, "data_conflict", "数据状态发生冲突，请刷新后重试")

    @application.exception_handler(OperationalError)
    async def database_error(request: Request, _exc: OperationalError):
        return error_response(
            request, 503, "database_unavailable", "数据库暂不可用，请检查迁移或稍后重试"
        )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            public_paths = {
                "/api/health",
                "/api/license/status",
                "/api/license/activate",
                "/api/license/verify",
            }
            if (
                request.url.path not in public_paths
                and not (await run_in_threadpool(runtime.status))["authorized"]
            ):
                response = error_response(
                    request, 403, "license_required", "软件尚未激活或授权已失效，请先验证授权"
                )
                response.headers["Cache-Control"] = "no-store"
            else:
                response = await call_next(request)
        except Exception as exc:
            # 异常边界只记录类型和关联 ID，不记录可能携带密钥的原始异常文本。
            logger.error(
                "请求处理失败 request_id=%s error_type=%s",
                request.state.request_id,
                type(exc).__name__,
            )
            return error_response(request, 500, "internal_error", "服务暂时异常，请稍后重试")
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path == "/api/health" and os.environ.get("AIFACE_INSTANCE"):
            response.headers["X-AIFACE-Instance"] = os.environ["AIFACE_INSTANCE"]
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = "请求的资源不存在" if exc.status_code == 404 else "请求无法处理"
        return error_response(request, exc.status_code, code, message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        # 不回显原始输入，避免敏感请求字段进入错误响应。
        return error_response(request, 422, "validation_error", "请求参数不正确，请检查后重试")

    @application.get("/api/health", tags=["系统"])
    def health(request: Request):
        try:
            with request.app.state.engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != request.app.state.schema_head:
                return error_response(
                    request, 503, "database_not_ready", "数据库尚未就绪，请先执行数据库迁移"
                )
        except SQLAlchemyError:
            return error_response(
                request, 503, "database_not_ready", "数据库尚未就绪，请检查连接并执行数据库迁移"
            )
        return {"status": "ok", "database": "ready", "version": "0.1.0"}

    return application
