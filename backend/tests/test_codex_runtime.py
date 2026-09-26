"""Codex 路径发现、保存及本地文件选择边界。"""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import codex_runtime
from app.services.orders import BusinessError


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_runtime, "CONFIG_PATH", tmp_path / "codex-settings.json")
    monkeypatch.setattr(codex_runtime, "automatic_candidates", lambda: [])
    monkeypatch.setattr(codex_runtime, "probe", lambda path: "codex-cli 1.0")
    return tmp_path


def executable(root):
    folder = root / "中文 带空格"
    folder.mkdir(parents=True)
    path = folder / "codex.exe"
    path.write_bytes(b"test")
    return path


def test_manual_path_persists_and_overrides_detection(runtime, monkeypatch):
    path = executable(runtime)
    monkeypatch.setattr(codex_runtime, "automatic_candidates", lambda: [("other", "PATH")])
    result = codex_runtime.save_path(str(path))
    assert result["available"] and result["source"] == "manual"
    assert result["resolved_path"] == str(path)
    assert codex_runtime.resolve_executable() == str(path)
    assert json.loads(codex_runtime.CONFIG_PATH.read_text(encoding="utf-8"))["path"] == str(path)


def test_missing_manual_path_does_not_silently_switch(runtime, monkeypatch):
    path = executable(runtime)
    codex_runtime.CONFIG_PATH.write_text(
        json.dumps({"path": str(path / "missing.exe")}), encoding="utf-8"
    )
    monkeypatch.setattr(codex_runtime, "automatic_candidates", lambda: [(path, "PATH")])
    assert not codex_runtime.status()["available"]
    with pytest.raises(BusinessError):
        codex_runtime.resolve_executable()


def test_clear_restores_auto_and_invalid_save_preserves_previous(runtime, monkeypatch):
    path = executable(runtime)
    codex_runtime.save_path(str(path))
    with pytest.raises(BusinessError):
        codex_runtime.save_path("relative.exe")
    assert codex_runtime.status()["configured_path"] == str(path)
    monkeypatch.setattr(codex_runtime, "automatic_candidates", lambda: [(path, "desktop")])
    result = codex_runtime.save_path("")
    assert result["configured_path"] == "" and result["source"] == "desktop"


def test_auto_skips_broken_candidate(runtime, monkeypatch):
    path = executable(runtime)
    monkeypatch.setattr(
        codex_runtime,
        "automatic_candidates",
        lambda: [(runtime / "missing.exe", "PATH"), (path, "desktop")],
    )
    assert codex_runtime.status()["resolved_path"] == str(path)


def test_desktop_discovery_without_path(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_runtime.shutil, "which", lambda _: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = tmp_path / "Programs/OpenAI/Codex/bin/codex.exe"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"cli")
    assert (path, "desktop") in list(codex_runtime.automatic_candidates())


def test_probe_rejects_timeout_and_non_cli(tmp_path, monkeypatch):
    path = executable(tmp_path)
    codex_runtime._probe_cached.cache_clear()
    monkeypatch.setattr(
        codex_runtime.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="unrelated", stderr=""),
    )
    with pytest.raises(BusinessError):
        codex_runtime.probe(str(path))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("codex", 8)

    monkeypatch.setattr(codex_runtime.subprocess, "run", timeout)
    with pytest.raises(BusinessError):
        codex_runtime.probe(str(path))


def test_settings_routes_and_local_only_picker(runtime, monkeypatch):
    path = executable(runtime)
    monkeypatch.setattr(codex_runtime, "choose_path", lambda: str(path))
    app = create_app(Settings(_env_file=None, AIFACE_DATABASE_PATH=runtime / "test.db"))
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        url = "/api/model-settings/codex"
        assert client.get(url).json()["available"] is False
        assert client.put(url, json={"path": str(path)}).json()["available"] is True
        assert (
            client.post(url + "/browse", headers={"origin": "https://remote.test"}).status_code
            == 403
        )
        assert client.post(url + "/browse", headers={"origin": "http://localhost:3000"}).json()[
            "path"
        ] == str(path)
        monkeypatch.setattr(codex_runtime, "choose_path", lambda: None)
        assert (
            client.post(url + "/browse", headers={"origin": "http://localhost:3000"}).json()["path"]
            is None
        )
        assert (
            client.post(
                url + "/browse",
                headers={"origin": "http://localhost:3000", "x-forwarded-for": "8.8.8.8"},
            ).status_code
            == 403
        )


def test_picker_child_returns_unicode_path(runtime, monkeypatch):
    path = executable(runtime)

    def run(command, **kwargs):
        assert command[-1] == "select-codex"
        assert "shell" not in kwargs
        return SimpleNamespace(returncode=0, stdout=json.dumps({"path": str(path)}))

    monkeypatch.setattr(codex_runtime.subprocess, "run", run)
    assert codex_runtime.choose_path() == str(path)


def test_npm_wrapper_uses_native_executable(tmp_path, monkeypatch):
    wrapper = tmp_path / "codex.cmd"
    monkeypatch.setattr(codex_runtime.shutil, "which", lambda _: str(wrapper))
    candidates = list(codex_runtime.automatic_candidates())
    assert all(path.suffix != ".cmd" for path, _ in candidates)
    assert any("codex-win32-x64" in str(path) and source == "npm" for path, source in candidates)


def test_frozen_picker_uses_own_exe_and_releases_lock_after_timeout(runtime, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    def timeout(command, **kwargs):
        assert command == [sys.executable, "select-codex"]
        raise subprocess.TimeoutExpired(command, 180)

    monkeypatch.setattr(codex_runtime.subprocess, "run", timeout)
    with pytest.raises(BusinessError) as error:
        codex_runtime.choose_path()
    assert error.value.code == "codex_picker_failed"
    assert not codex_runtime.PICKER_LOCK.locked()


def test_native_dialog_cancel_destroys_root(monkeypatch, capsys):
    destroyed = []
    window = SimpleNamespace(
        withdraw=lambda: None, attributes=lambda *a: None, destroy=lambda: destroyed.append(True)
    )
    filedialog = SimpleNamespace(askopenfilename=lambda **kwargs: "")
    monkeypatch.setitem(
        sys.modules, "tkinter", SimpleNamespace(Tk=lambda: window, filedialog=filedialog)
    )
    assert codex_runtime.picker_main() == 0
    assert json.loads(capsys.readouterr().out) == {"path": None}
    assert destroyed == [True]
