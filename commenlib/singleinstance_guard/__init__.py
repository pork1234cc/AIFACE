# -*- coding: utf-8 -*-
"""
singleinstance_guard - 可复用的 Windows 单实例锁 + 残留进程自动清理模块

平台要求：仅支持 Windows（依赖 Mutex 内核对象与 taskkill 命令）

典型用法（必须在 tk.Tk() 创建之前调用）：

    import sys
    from singleinstance_guard import SingleInstanceGuardConfig, acquire_single_instance

    cfg = SingleInstanceGuardConfig(
        mutex_name=r"Global\YourApp_SingleInstance",
    )
    if not acquire_single_instance(cfg):
        # 已有实例在运行（或清理失败）→ 调用方自行弹窗 + 退出
        import tkinter.messagebox as mb
        mb.showwarning("提示", "程序已在运行")
        sys.exit(0)
"""
from .config import SingleInstanceGuardConfig
from .guard import acquire_single_instance

__all__ = [
    "SingleInstanceGuardConfig",
    "acquire_single_instance",
]
