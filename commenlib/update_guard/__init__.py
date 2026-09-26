# -*- coding: utf-8 -*-
"""
update_guard - 可复用的版本更新检查模块

使用方式（核心，无 UI 依赖）:
    from update_guard import UpdateGuardConfig, check_update

    config = UpdateGuardConfig(
        check_url="https://your-host.com/version.json",
        current_version="1.0",
    )
    result = check_update(config)
    if result.has_update:
        print(f"新版本: {result.latest_version}")

使用方式（tkinter 一行集成）:
    from update_guard import UpdateGuardConfig, check_update_tk

    check_update_tk(widget, config)
"""
from .config import UpdateGuardConfig
from .checker import check_update, check_update_async, UpdateResult
from .tk_helper import check_update_tk

__all__ = [
    "UpdateGuardConfig",
    "UpdateResult",
    "check_update",
    "check_update_async",
    "check_update_tk",
]
