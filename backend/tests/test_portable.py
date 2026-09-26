"""便携入口的环境隔离、端口检查与 Windows 子进程回收。"""

import os
import socket
import subprocess
import sys

import httpx
import pytest

from app.portable import (
    ProcessJob,
    check_ports,
    initialize_config,
    portable_environment,
    wait_ready,
)


def test_portable_environment_does_not_inherit_business_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("image_api", "private-development-key")
    monkeypatch.setenv("AIFACE_DATABASE_PATH", "private.sqlite3")
    monkeypatch.setenv("NODE_OPTIONS", "--require=unexpected.js")
    monkeypatch.setenv("PYTHONPATH", "another-project")
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    env = portable_environment(tmp_path)
    assert "image_api" not in env
    assert "NODE_OPTIONS" not in env
    assert "PYTHONPATH" not in env
    assert env["AIFACE_DATABASE_PATH"] == str(tmp_path / "storage/unified/database/aiface.sqlite3")
    assert env["APPDATA"] == str(tmp_path / "profile")


def test_existing_configuration_is_never_overwritten(tmp_path):
    target = tmp_path / ".env"
    target.write_text("image_api=user-owned-key\n", encoding="utf-8")
    initialize_config(tmp_path)
    assert target.read_text(encoding="utf-8") == "image_api=user-owned-key\n"


def test_occupied_port_is_reported_without_stopping_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match=str(port)):
            check_ports([port])
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass


@pytest.mark.skipif(os.name != "nt", reason="Windows 进程生命周期验证")
def test_job_closes_owned_background_process():
    with ProcessJob() as job:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        job.assign(process)
        assert process.poll() is None
    process.wait(timeout=10)
    assert process.returncode is not None


def test_ready_check_rejects_other_server(monkeypatch):
    monkeypatch.setattr("app.portable.time.sleep", lambda _: None)
    response = httpx.Response(200, json={"status": "ok"})
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
        with pytest.raises(RuntimeError, match="启动超时"):
            wait_ready(client, "http://127.0.0.1/api/health", [], "expected", timeout=0.01)


def test_ready_check_stops_when_child_exits():
    class Failed:
        def poll(self):
            return 1

    with httpx.Client() as client:
        with pytest.raises(RuntimeError, match="服务提前退出"):
            wait_ready(client, "http://127.0.0.1/api/health", [Failed()], "expected")
