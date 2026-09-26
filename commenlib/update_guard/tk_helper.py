# -*- coding: utf-8 -*-
"""
update_guard tkinter 便捷集成

提供一行调用即可完成「后台检查 + UI 弹窗提示」的辅助函数。
"""
import webbrowser
import tkinter.messagebox as messagebox

from .config import UpdateGuardConfig
from .checker import check_update_async, UpdateResult


def check_update_tk(widget, config: UpdateGuardConfig):
    """
    tkinter 一行调用：后台检查更新，自动在 UI 线程弹窗。

    Args:
        widget: 任意 tkinter 组件（用于 .after() 调度）
        config: UpdateGuardConfig 实例
    """
    def _on_result(result: UpdateResult):
        if result.error:
            widget.after(0, lambda: messagebox.showwarning(
                "检查更新", "无法连接更新服务器，请检查网络"))
        elif result.has_update:
            widget.after(0, lambda: _prompt_update(config.current_version, result))
        else:
            widget.after(0, lambda: messagebox.showinfo(
                "检查更新", f"当前已是最新版本 (v{config.current_version})"))

    check_update_async(config, _on_result)


def _prompt_update(current_version: str, result: UpdateResult):
    """显示更新提示对话框"""
    msg = f"发现新版本: v{result.latest_version}（当前 v{current_version}）"
    if result.changelog:
        msg += f"\n\n更新内容:\n{result.changelog}"
    msg += "\n\n是否前往下载？"
    if messagebox.askyesno("检查更新", msg) and result.download_url:
        webbrowser.open(result.download_url)
