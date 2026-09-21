"""当前 Apii 协议的本地模型配置。密钥只保存到已有的后端 .env。"""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.config import Settings

FIELDS = {"image_api_url", "image_model", "image_quality", "image_api"}


class ModelSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=80)
    quality: str
    api_key: SecretStr | None = Field(default=None, repr=False)


def public_settings(settings: Settings) -> dict:
    return {
        "api_url": settings.image_api_url,
        "model": settings.image_model,
        "quality": settings.image_quality,
        "has_api_key": settings.image_api is not None,
    }


def save_settings(path: Path, payload: ModelSettingsRequest) -> Settings:
    existing = Settings(_env_file=path)
    key = payload.api_key.get_secret_value().strip() if payload.api_key is not None else ""
    if not key:
        key = existing.image_api.get_secret_value() if existing.image_api else ""
    if any(character in key for character in "\r\n\0"):
        raise ValueError("API Key 不能包含换行或空字符")
    validated = Settings(
        _env_file=None,
        image_api_url=payload.api_url,
        image_model=payload.model,
        image_quality=payload.quality,
        image_api=key,
    )
    values = {
        "image_api_url": validated.image_api_url,
        "image_model": validated.image_model,
        "image_quality": validated.image_quality,
        "image_api": key,
    }
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines()
    kept = [
        line
        for line in lines
        if not (match := re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line))
        or match.group(1) not in FIELDS
    ]
    kept.extend(f"{name}={json.dumps(value, ensure_ascii=False)}" for name, value in values.items())
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(kept) + "\n")
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)
    return Settings(_env_file=path)
