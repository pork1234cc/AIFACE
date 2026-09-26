# -*- coding: utf-8 -*-
"""
license_guard 使用示例

平台要求：仅支持 Windows

激活服务端需实现以下两个接口：

POST {server_url}/activate
    请求体：{"license_key": "XXXX-XXXX-XXXX-XXXX", "machine_code": "abc123..."}
    成功响应：{"status": "ok", "expire_date": "2025-12-31", "license_type": "standard"}
    失败响应：{"status": "error", "message": "激活码无效"}

POST {server_url}/verify
    请求体：{"license_key": "XXXX-XXXX-XXXX-XXXX", "machine_code": "abc123..."}
    成功响应：{"status": "ok", "expire_date": "2025-12-31", "license_type": "standard"}
    失败响应：{"status": "error", "message": "激活码已过期"}
"""
import tkinter as tk
from license_guard import LicenseGuardConfig, LicenseClient, LicenseGUI

# ---- 配置（移植时只改这里）---- #
config = LicenseGuardConfig(
    server_url="https://your-server.com/api",   # 激活服务端地址
    product_id="your_product_id",               # 产品ID（同时用作数据目录名）
    # app_title="软件激活",                      # 可选：激活窗口标题
    # app_heading="请输入激活码",                # 可选：窗口内标题文字
    # code_hint="XXXX-XXXX-XXXX-XXXX",          # 可选：激活码格式提示
    # offline_grace_days=7,                      # 可选：允许离线使用的天数
    # legacy_dirs=[r"C:\old_app_data"],          # 可选：旧版数据目录（迁移用）
)
# -------------------------------- #


def example_verify_only():
    """仅验证激活状态（无 UI）"""
    client = LicenseClient(config)
    ok, msg, info = client.verify()
    if ok:
        print(f"已激活，到期：{info.get('expire_date', '永久')}")
    else:
        print(f"未激活：{msg}")
    return ok


def example_with_activation_window():
    """完整流程：验证失败时弹出激活窗口"""
    client = LicenseClient(config)
    ok, msg, info = client.verify()

    if not ok:
        # 弹出激活窗口（阻塞，用户完成激活或关闭后返回）
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        gui = LicenseGUI(root, config, client)
        gui.show()
        root.destroy()

        # 激活后再验证一次
        ok, msg, info = client.verify()
        if not ok:
            print("用户未完成激活，程序退出")
            return

    # 激活通过，进入主程序
    print("激活验证通过，启动主程序...")
    main_app()


def main_app():
    """主程序（激活通过后执行）"""
    root = tk.Tk()
    root.title("主程序")
    root.geometry("600x400")
    tk.Label(root, text="程序已激活，正常运行中").pack(pady=20)
    root.mainloop()


if __name__ == "__main__":
    example_with_activation_window()
