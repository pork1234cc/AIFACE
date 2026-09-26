"""验证配置缺失、路径稳定性和密钥脱敏。"""

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings, runtime_roots


def test_frozen_resources_and_writable_data_are_separate(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "resources"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "portable" / "AIFACE.exe"))
    resources, data = runtime_roots()
    assert resources == tmp_path / "resources"
    assert data == tmp_path / "portable"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_key_allows_startup_but_blocks_model_use(monkeypatch, value):
    monkeypatch.delenv("image_api", raising=False)
    settings = Settings(_env_file=None, image_api=value)
    with pytest.raises(RuntimeError, match="尚未配置 image_api"):
        settings.require_image_api()


def test_secret_is_not_serialized_or_printed():
    secret = "test-secret-never-return"
    settings = Settings(_env_file=None, image_api=secret)
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
    assert settings.require_image_api() == secret


def test_relative_database_path_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, AIFACE_DATABASE_PATH="storage/database/test.sqlite3")
    assert settings.database_path == PROJECT_ROOT / "storage/database/test.sqlite3"


@pytest.mark.parametrize("value", ["", "   ", PROJECT_ROOT])
def test_invalid_database_path_has_clear_error(value):
    with pytest.raises(ValidationError, match="AIFACE_DATABASE_PATH"):
        Settings(_env_file=None, AIFACE_DATABASE_PATH=value)


def test_utf8_env_file_loads_secret_without_revealing_it(tmp_path, monkeypatch):
    monkeypatch.delenv("image_api", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# 本地模型配置\nimage_api=test-file-secret\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.require_image_api() == "test-file-secret"
    assert "test-file-secret" not in settings.model_dump_json()
