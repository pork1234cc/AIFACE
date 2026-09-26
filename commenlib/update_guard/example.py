# -*- coding: utf-8 -*-
"""
update_guard 使用示例

服务端需提供一个 JSON 文件（如 version.json），格式如下：
{
    "latest_version": "1.2.0",
    "download_url": "https://your-server.com/download/app_v1.2.0.exe",
    "changelog": "修复若干问题，优化性能"
}

字段名可通过 UpdateGuardConfig 的 field_* 参数自定义，以适配不同服务端 schema。
"""
import tkinter as tk
from update_guard import UpdateGuardConfig, check_update, check_update_tk

# ---- 配置（移植时只改这里）---- #
config = UpdateGuardConfig(
    check_url="https://your-server.com/version.json",  # version.json 地址
    current_version="1.0.0",                           # 当前软件版本号
    # timeout=10,                                      # 可选：HTTP 超时秒数
    # field_latest_version="latest_version",           # 可选：JSON 字段名映射
    # field_download_url="download_url",
    # field_changelog="changelog",
)
# -------------------------------- #


def example_sync():
    """同步调用示例（适合非 UI 场景）"""
    result = check_update(config)
    if result.error:
        print(f"检查失败：{result.error}")
    elif result.has_update:
        print(f"有新版本：{result.latest_version}")
        print(f"下载地址：{result.download_url}")
        print(f"更新日志：{result.changelog}")
    else:
        print(f"已是最新版本（{config.current_version}）")


def example_tkinter():
    """Tkinter 集成示例（一行调用，自动弹窗）"""
    root = tk.Tk()
    root.title("示例程序")
    root.geometry("400x300")

    # 窗口加载后自动在后台检查更新，有新版本时弹窗提示
    check_update_tk(root, config)

    root.mainloop()


if __name__ == "__main__":
    # 运行同步示例
    example_sync()

    # 运行 Tkinter 示例（取消注释）
    # example_tkinter()
