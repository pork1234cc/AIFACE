"""项目配置：路径固定相对项目根目录，密钥只在后端读取。"""

import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def runtime_roots() -> tuple[Path, Path]:
    """冻结时分开只读资源和可写数据，开发态保持原目录布局。"""
    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
        return Path(getattr(sys, "_MEIPASS", executable_root)), executable_root
    root = Path(__file__).resolve().parents[2]
    return root, root


PROJECT_ROOT, DATA_ROOT = runtime_roots()
SETTINGS_FILE = DATA_ROOT / ".env"
DEFAULT_IMAGE_API_URL = "https://ai.apii.cn"
DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SETTINGS_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    image_api: SecretStr | None = Field(default=None, repr=False, exclude=True)
    image_api_url: str = DEFAULT_IMAGE_API_URL
    image_model: str = DEFAULT_IMAGE_MODEL
    image_quality: str = "high"
    database_path: Path = Field(
        default=DATA_ROOT / "storage/unified/database/aiface.sqlite3",
        validation_alias="AIFACE_DATABASE_PATH",
    )
    storage_path: Path = Field(
        default=DATA_ROOT / "storage/unified",
        validation_alias="AIFACE_STORAGE_PATH",
    )

    @field_validator("storage_path", mode="before")
    @classmethod
    def resolve_storage_path(cls, value: str | Path) -> Path:
        if isinstance(value, str) and not value.strip():
            raise ValueError("AIFACE_STORAGE_PATH 不能为空")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = DATA_ROOT / path
        if path.is_file():
            raise ValueError("AIFACE_STORAGE_PATH 必须是目录")
        return path.resolve()

    @field_validator("image_api", mode="before")
    @classmethod
    def normalize_key(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("image_api_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.port == 0
        ):
            raise ValueError("接口 URL 必须是 HTTPS 地址，且不含路径、参数或账号")
        return value.strip().rstrip("/")

    @field_validator("image_model")
    @classmethod
    def validate_image_model(cls, value: str) -> str:
        model = value.strip()
        if not model or len(model) > 80 or any(char.isspace() for char in model):
            raise ValueError("模型名称须为 1～80 个非空白字符")
        return model

    @field_validator("image_quality")
    @classmethod
    def validate_image_quality(cls, value: str) -> str:
        if value not in {"auto", "low", "medium", "high"}:
            raise ValueError("质量必须为 auto、low、medium 或 high")
        return value

    @field_validator("database_path", mode="before")
    @classmethod
    def resolve_database_path(cls, value: str | Path) -> Path:
        if isinstance(value, str) and not value.strip():
            raise ValueError("AIFACE_DATABASE_PATH 不能为空")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = DATA_ROOT / path
        path = path.resolve()
        if path.is_dir():
            raise ValueError("AIFACE_DATABASE_PATH 必须指向数据库文件，不能是目录")
        return path

    def require_image_api(self) -> str:
        if self.image_api is None:
            raise RuntimeError("尚未配置 image_api，请在项目根目录 .env 中填写模型密钥")
        return self.image_api.get_secret_value()
