# -*- coding: utf-8 -*-
"""
update_guard 核心检查逻辑（无 UI 依赖）
"""
import threading
from dataclasses import dataclass
from typing import Optional, Callable

from .config import UpdateGuardConfig


@dataclass
class UpdateResult:
    """更新检查结果"""
    has_update: bool
    latest_version: str = ""
    download_url: str = ""
    changelog: str = ""
    error: Optional[str] = None  # 非 None 表示检查失败


def version_tuple(v: str) -> tuple:
    """将版本号字符串转为可比较的元组，如 "1.2.3" -> (1, 2, 3)"""
    return tuple(int(x) for x in v.strip().split("."))


def check_update(config: UpdateGuardConfig) -> UpdateResult:
    """
    同步检查更新。

    Args:
        config: 更新检查配置

    Returns:
        UpdateResult 实例
    """
    import requests

    try:
        resp = requests.get(config.check_url, timeout=config.timeout)
        if resp.status_code != 200:
            return UpdateResult(has_update=False, error=f"更新服务器返回 HTTP {resp.status_code}")

        data = resp.json()
        latest = data.get(config.field_latest_version, "")
        download_url = data.get(config.field_download_url, "")
        changelog = data.get(config.field_changelog, "")

        if latest and version_tuple(latest) > version_tuple(config.current_version):
            return UpdateResult(
                has_update=True,
                latest_version=latest,
                download_url=download_url,
                changelog=changelog,
            )
        return UpdateResult(has_update=False, latest_version=latest)
    except Exception as e:
        return UpdateResult(has_update=False, error=str(e))


def check_update_async(
    config: UpdateGuardConfig,
    callback: Callable[[UpdateResult], None],
):
    """
    异步检查更新（后台线程）。

    callback 在工作线程中调用，调用方需自行调度到 UI 线程。

    Args:
        config: 更新检查配置
        callback: 接收 UpdateResult 的回调函数
    """
    def _worker():
        result = check_update(config)
        callback(result)

    threading.Thread(target=_worker, daemon=True).start()
