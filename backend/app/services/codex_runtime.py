"""发现本机 Codex、保存手动路径，并在独立进程打开文件选择窗口。"""

import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.config import DATA_ROOT, PROJECT_ROOT
from app.services.orders import BusinessError

CONFIG_PATH = DATA_ROOT / "codex-settings.json"
PICKER_LOCK = Lock()


def automatic_candidates():
    """只检查 PATH 和已知安装目录，不递归搜索整块磁盘。"""
    for command in ("codex.exe", "codex"):
        found = shutil.which(command)
        if found:
            path = Path(found)
            if path.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
                yield path, "PATH"
            else:
                yield from npm_candidates(path.parent / "node_modules/@openai")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for relative in (
            "Programs/OpenAI/Codex/bin/codex.exe",
            "Programs/OpenAI/Codex/resources/codex.exe",
            "Programs/Codex/bin/codex.exe",
            "Programs/Codex/resources/codex.exe",
        ):
            yield Path(local) / relative, "desktop"
    roaming = os.environ.get("APPDATA")
    if roaming:
        yield from npm_candidates(Path(roaming) / "npm/node_modules/@openai")
    for variable in ("ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if not base:
            continue
        apps = Path(base) / (
            "WindowsApps" if variable == "ProgramFiles" else "Microsoft/WindowsApps"
        )
        try:
            for folder in apps.glob("OpenAI.Codex_*"):
                for relative in ("app/bin/codex.exe", "app/resources/codex.exe", "bin/codex.exe"):
                    yield folder / relative, "desktop"
        except OSError:
            continue


def npm_candidates(root: Path):
    for base in (root, root / "codex/node_modules/@openai"):
        for arch, triple in (("x64", "x86_64"), ("arm64", "aarch64")):
            yield (
                base / f"codex-win32-{arch}/vendor/{triple}-pc-windows-msvc/codex/codex.exe",
                "npm",
            )
    for triple in ("x86_64", "aarch64"):
        yield root / f"codex/vendor/{triple}-pc-windows-msvc/codex/codex.exe", "npm"


def configured_path() -> str:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("path"), str):
            raise ValueError("配置格式不正确")
        return data["path"]
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as exc:
        raise BusinessError(
            503, "codex_config_invalid", "Codex 路径配置无法读取，请重新保存"
        ) from exc


def validate_path(value: str) -> Path:
    path = Path(value)
    if (
        not value
        or any(char in value for char in "\r\n\0")
        or not path.is_absolute()
        or path.name.lower() not in {"codex.exe", "codex"}
        or not path.is_file()
    ):
        raise BusinessError(
            422, "codex_path_invalid", "请选择存在的 Codex 可执行文件（codex.exe）绝对路径"
        )
    # 保留安装入口的符号链接，避免把可更新入口固定到某个版本目录。
    return path.absolute()


@lru_cache(maxsize=16)
def _probe_cached(path: str, modified: int, size: int) -> str:
    try:
        options = {
            "capture_output": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 8,
            "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        }
        version = subprocess.run([path, "--version"], **options)
        if version.returncode != 0 or not re.match(
            r"^codex-cli\s+[\w.+-]+", version.stdout.strip()
        ):
            raise ValueError("不是 Codex CLI")
        help_result = subprocess.run([path, "exec", "--help"], **options)
        if help_result.returncode != 0 or "--output-schema" not in help_result.stdout:
            raise ValueError("不支持结构化分析")
        return version.stdout.strip().splitlines()[0][:100]
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise BusinessError(
            422, "codex_probe_failed", "该程序无法运行或不支持 Codex 结构化分析，请检查 CLI 版本"
        ) from exc


def probe(path: str) -> str:
    stat = Path(path).stat()
    return _probe_cached(path, stat.st_mtime_ns, stat.st_size)


def status(manual: str | None = None) -> dict:
    try:
        selected = configured_path() if manual is None else manual
    except BusinessError as exc:
        return {
            "configured_path": "",
            "resolved_path": "",
            "source": "",
            "available": False,
            "version": "",
            "message": exc.message,
        }
    message = "未找到 Codex，请浏览选择 codex.exe，或安装 Codex CLI"
    seen = set()
    for candidate, source in [(selected, "manual")] if selected else automatic_candidates():
        if str(candidate).lower() in seen:
            continue
        seen.add(str(candidate).lower())
        try:
            path = validate_path(str(candidate))
            version = probe(str(path))
            return {
                "configured_path": selected,
                "resolved_path": str(path),
                "source": source,
                "available": True,
                "version": version,
                "message": "Codex CLI 可用",
            }
        except (OSError, BusinessError) as exc:
            if selected:
                message = exc.message if isinstance(exc, BusinessError) else "Codex 文件无法读取"
    return {
        "configured_path": selected,
        "resolved_path": "",
        "source": "manual" if selected else "",
        "available": False,
        "version": "",
        "message": message,
    }


def save_path(value: str) -> dict:
    value = value.strip()
    result = status(value)
    if value and not result["available"]:
        raise BusinessError(422, "codex_path_invalid", result["message"])
    normalized = result["resolved_path"] if value else ""
    pending = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.{uuid4().hex}.tmp")
    with pending.open("x", encoding="utf-8") as stream:
        json.dump({"path": normalized}, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, CONFIG_PATH)
    return {**result, "configured_path": normalized}


def resolve_executable() -> str:
    result = status()
    if not result["available"]:
        raise BusinessError(503, "codex_unavailable", result["message"] + "；请前往模型设置")
    return result["resolved_path"]


def choose_path() -> str | None:
    if not PICKER_LOCK.acquire(blocking=False):
        raise BusinessError(409, "codex_picker_busy", "文件选择窗口已打开，请先完成选择")
    try:
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(PROJECT_ROOT / "main.py"))
        result = subprocess.run(
            [*command, "select-codex"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            raise ValueError("文件选择失败")
        value = json.loads(result.stdout)["path"]
        if value is not None and not isinstance(value, str):
            raise ValueError("文件选择格式不正确")
        return value
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        raise BusinessError(
            503, "codex_picker_failed", "文件选择已超时或无法打开，请直接粘贴完整路径"
        ) from exc
    finally:
        PICKER_LOCK.release()


def picker_main() -> int:
    """Tk 只在专用子进程主线程运行，取消不修改配置。"""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askopenfilename(
            parent=root,
            title="选择 Codex CLI（codex.exe）",
            filetypes=[("Codex CLI", "codex.exe"), ("可执行文件", "*.exe")],
        )
        print(json.dumps({"path": path or None}, ensure_ascii=False))
        return 0
    finally:
        root.destroy()
