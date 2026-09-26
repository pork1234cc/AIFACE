"""便携启动器：使用随包环境并管理自己的服务进程。"""

import ctypes
import os
import socket
import subprocess
import sys
import time
import webbrowser
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

import httpx

from app.config import DATA_ROOT, PROJECT_ROOT

API_PORT = 18480
WEB_PORT = 18481


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", ctypes.c_ulonglong * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class ProcessJob:
    """窗口被关闭时也由操作系统回收本启动器的后台进程。"""

    def __enter__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = ExtendedLimits()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.kernel.CloseHandle(self.handle)
            raise error
        return self

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            error = ctypes.WinError(ctypes.get_last_error())
            process.terminate()
            process.wait(timeout=10)
            raise error

    def __exit__(self, *_):
        self.kernel.CloseHandle(self.handle)


def check_ports(ports):
    for port in ports:
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(
                    f"端口 {port} 已被占用，请先退出另一份 AIFACE 或占用程序"
                ) from exc


def portable_environment(root: Path):
    env = os.environ.copy()
    # 使用本便携目录的数据与随包运行环境，防止继承开发环境的路径和密钥。
    for key in list(env):
        if key.upper().startswith(("PYTHON", "AIFACE_", "NEXT_", "IMAGE_")) or key.upper() in {
            "VIRTUAL_ENV",
            "NODE_PATH",
            "NODE_OPTIONS",
        }:
            env.pop(key)
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "AIFACE_DATABASE_PATH": str(root / "storage/unified/database/aiface.sqlite3"),
            "AIFACE_STORAGE_PATH": str(root / "storage/unified"),
            "AIFACE_INSTANCE": uuid4().hex,
            "NODE_ENV": "production",
            "NEXT_TELEMETRY_DISABLED": "1",
            "HOSTNAME": "127.0.0.1",
            "PORT": str(WEB_PORT),
        }
    )
    return env


def initialize_config(root: Path):
    try:
        with (root / ".env").open("x", encoding="utf-8") as target:
            target.write((PROJECT_ROOT / ".env.example").read_text(encoding="utf-8"))
    except FileExistsError:
        pass


def wait_ready(client, url, processes, instance, *, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("服务提前退出，请查看 storage/logs 中本次日志")
        try:
            response = client.get(url, timeout=2)
            if (
                response.status_code == 200
                and response.json().get("status") == "ok"
                and response.headers.get("X-AIFACE-Instance") == instance
            ):
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.3)
    raise RuntimeError("启动超时，请查看 storage/logs 中本次日志")


def run_portable(*, smoke_test=False):
    root = DATA_ROOT
    node = root / "runtime/node.exe"
    server = root / "frontend/server.js"
    if not node.is_file() or not server.is_file():
        raise RuntimeError("便携包不完整，请将整个压缩包解压后运行 AIFACE.exe")
    check_ports([API_PORT, WEB_PORT])
    initialize_config(root)
    env = portable_environment(root)
    logs = root / "storage/logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(PROJECT_ROOT / "main.py"))
    processes, streams = [], []
    try:
        with ProcessJob() as job, httpx.Client(trust_env=False) as client:

            def start(args, name, cwd=root):
                stream = (logs / f"{stamp}-{name}.log").open("w", encoding="utf-8")
                streams.append(stream)
                process = subprocess.Popen(
                    args,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                processes.append(process)
                job.assign(process)
                return process

            migration = start([*command, "migrate"], "migration")
            if migration.wait(timeout=60) != 0:
                raise RuntimeError("数据库初始化失败，请查看本次 migration 日志")
            processes.remove(migration)
            start([*command, "api", "--port", str(API_PORT)], "api")
            wait_ready(
                client, f"http://127.0.0.1:{API_PORT}/api/health", processes, env["AIFACE_INSTANCE"]
            )
            start([str(node), str(server)], "frontend", server.parent)
            base = f"http://127.0.0.1:{WEB_PORT}"
            wait_ready(client, base + "/api/health", processes, env["AIFACE_INSTANCE"])
            if smoke_test:
                import io

                import numpy as np
                from PIL import Image

                from app.services.element_masks import segment
                from app.services.elements import Element
                from app.services.regions import MODEL_PATH, model_session

                session = model_session(str(MODEL_PATH))
                result = session.run(
                    None,
                    {session.get_inputs()[0].name: np.zeros((1, 3, 512, 512), dtype=np.float32)},
                )
                if result[0].shape != (1, 19, 512, 512):
                    raise RuntimeError("随包区域模型推理检查失败")
                picture = Image.new("RGB", (128, 96), "white")
                picture.paste("red", (32, 24, 96, 72))
                data = io.BytesIO()
                picture.save(data, format="PNG")
                mask = segment(
                    data.getvalue(),
                    Element(
                        id="red_rectangle",
                        parent_id=None,
                        label="红色矩形",
                        target_description="画面中央的红色矩形",
                        kind="object",
                        bbox=[250, 250, 750, 750],
                        positive_points=[[500, 500]],
                        negative_points=[],
                    ),
                )
                if (
                    mask["width"] != 128
                    or mask["height"] != 96
                    or mask["location_status"] != "located"
                    or not mask["mask_runs"]
                ):
                    raise RuntimeError("随包对象轮廓模型推理检查失败")
                page = client.get(base, timeout=15)
                if page.status_code != 200 or "激活软件" not in page.text:
                    raise RuntimeError("便携前端授权入口检查失败")
                status = client.get(base + "/api/license/status", timeout=60).json()
                if status["authorized"]:
                    raise RuntimeError("冒烟测试应使用隔离的未激活用户目录")
                if client.get(base + "/api/orders", timeout=10).status_code != 403:
                    raise RuntimeError("未激活的业务接口没有正确拦截")
                print(
                    "便携 EXE 冒烟通过：空库、前端、API、授权门禁、区域及对象轮廓模型推理正常；"
                    "未启动生成 Worker，未调用 Codex。"
                )
                return 0
            start([*command, "worker", "--port", str(API_PORT)], "worker")
            webbrowser.open(base)
            print(f"AIFACE 已启动：{base}\n保留此窗口；按 Ctrl+C 或关闭窗口退出。", flush=True)
            while all(process.poll() is None for process in processes):
                time.sleep(1)
            raise RuntimeError("服务意外退出，请查看 storage/logs 中本次日志")
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.wait(timeout=15)
        for stream in streams:
            stream.close()
