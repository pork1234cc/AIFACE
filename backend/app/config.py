"""项目配置：路径固定相对项目根目录，密钥只在后端读取。"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    image_api: SecretStr | None = Field(default=None, repr=False, exclude=True)
    database_path: Path = Field(
        default=PROJECT_ROOT / "storage/database/aiface.sqlite3",
        validation_alias="AIFACE_DATABASE_PATH",
    )
    storage_path: Path = Field(
        default=PROJECT_ROOT / "storage",
        validation_alias="AIFACE_STORAGE_PATH",
    )

    @field_validator("storage_path", mode="before")
    @classmethod
    def resolve_storage_path(cls, value: str | Path) -> Path:
        if isinstance(value, str) and not value.strip():
            raise ValueError("AIFACE_STORAGE_PATH 不能为空")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.is_file():
            raise ValueError("AIFACE_STORAGE_PATH 必须是目录")
        return path.resolve()

    @field_validator("image_api", mode="before")
    @classmethod
    def normalize_key(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("database_path", mode="before")
    @classmethod
    def resolve_database_path(cls, value: str | Path) -> Path:
        if isinstance(value, str) and not value.strip():
            raise ValueError("AIFACE_DATABASE_PATH 不能为空")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path = path.resolve()
        if path.is_dir():
            raise ValueError("AIFACE_DATABASE_PATH 必须指向数据库文件，不能是目录")
        return path

    def require_image_api(self) -> str:
        if self.image_api is None:
            raise RuntimeError("尚未配置 image_api，请在项目根目录 .env 中填写模型密钥")
        return self.image_api.get_secret_value()
