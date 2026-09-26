# -*- coding: utf-8 -*-
"""
singleinstance_guard 使用示例

平台要求：仅支持 Windows

行为说明：
- 开发态（python.exe）：检测到残留时直接返回 False，绝不尝试 taskkill，
  避免误杀其他 Python 进程。
- 打包态（sys.frozen=True）：默认同样返回 False，保留正在运行的实例。
- 只有显式设置 kill_stale_in_frozen=True 才会强制结束同名进程及其子进程。
"""
import sys
import logging
import tkinter as tk
import tkinter.messagebox as mb

from singleinstance_guard import SingleInstanceGuardConfig, acquire_single_instance

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ---- 配置（移植时只改这里）---- #
config = SingleInstanceGuardConfig(
    mutex_name=r"Global\YourApp_SingleInstance",   # 必填：全局唯一的 Mutex 名
    # kill_stale_in_frozen=False,                   # 默认保留已有进程
    # poll_retries=5,                               # 可选：清理后轮询次数
    # poll_interval=0.2,                            # 可选：轮询间隔（秒）
    # taskkill_timeout=5,                           # 可选：taskkill 超时（秒）
)
# -------------------------------- #


def example_basic():
    """最小化集成示例：在 main 入口最早调用，必须早于 tk.Tk()。"""
    # 建议宿主项目自行 logging.basicConfig() 配置日志，本模块只发到
    # logger("singleinstance_guard")，默认有 NullHandler 兜底。
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not acquire_single_instance(config):
        # 已有实例在运行 → 弹窗提示并退出
        root = tk.Tk()
        root.withdraw()
        mb.showwarning("提示", "程序已在运行")
        root.destroy()
        sys.exit(0)

    # 拿到单实例锁，正常启动主程序
    root = tk.Tk()
    root.title("示例程序（已获取单实例锁）")
    root.geometry("400x200")
    tk.Label(root, text="程序运行中。\n再次启动会提示程序已在运行。", pady=40).pack()
    root.mainloop()


if __name__ == "__main__":
    example_basic()
