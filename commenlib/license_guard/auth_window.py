# -*- coding: utf-8 -*-
"""
激活窗口 — 在线卡密验证

流程: 输入激活码 -> 联网验证 -> 绑定机器码 -> 进入主程序
"""
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import sys
import threading

from .config import LicenseGuardConfig
from .license_client import LicenseClient


class LicenseGUI:
    """激活窗口"""

    def __init__(self, root, on_success, config: LicenseGuardConfig, client=None):
        self.root = root
        self.on_success = on_success
        self.config = config
        self.client = client if client is not None else LicenseClient(config)

        self.root.title(config.app_title)
        w, h = config.window_width, config.window_height
        self.root.geometry(f"{w}x{h}")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        self.root.protocol("WM_DELETE_WINDOW", lambda: sys.exit())

        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=self.config.app_heading,
            font=("微软雅黑", 14, "bold")
        ).pack(pady=(0, 20))

        ttk.Label(frame, text="请输入激活码:", font=("微软雅黑", 10)).pack(anchor="w")

        self.code_entry = ttk.Entry(frame, font=("Consolas", 12))
        self.code_entry.pack(fill=tk.X, pady=(5, 5))
        self.code_entry.bind('<Return>', lambda e: self.do_activate())

        ttk.Label(
            frame, text=f"激活码格式: {self.config.code_hint}",
            font=("微软雅黑", 9), foreground="gray"
        ).pack(anchor="w", pady=(0, 5))

        self.status_label = ttk.Label(frame, text="", font=("微软雅黑", 9))
        self.status_label.pack(anchor="w", pady=(0, 10))

        self.btn_activate = ttk.Button(
            frame, text="立 即 激 活", command=self.do_activate
        )
        self.btn_activate.pack(fill=tk.X, ipady=8)

    def do_activate(self):
        code = self.code_entry.get().strip()
        if not code:
            messagebox.showwarning("提示", "请输入激活码")
            return

        self.btn_activate.config(state=tk.DISABLED)
        self.status_label.config(text="正在联网验证...", foreground="blue")

        def _activate():
            ok, msg, data = self.client.activate(code)
            self.root.after(0, lambda: self._on_activate_result(ok, msg, data))

        threading.Thread(target=_activate, daemon=True).start()

    def _on_activate_result(self, ok, msg, data):
        self.btn_activate.config(state=tk.NORMAL)

        if ok:
            expire = data.get("expire_time", "")
            card_type = data.get("card_type", "")
            detail = f"{msg}"
            if card_type:
                detail += f"\n卡类型: {card_type}"
            if expire and expire != "9999-12-31 23:59:59":
                detail += f"\n有效期至: {expire}"
            elif expire == "9999-12-31 23:59:59":
                detail += "\n有效期: 永久"

            messagebox.showinfo("激活成功", detail)
            for widget in self.root.winfo_children():
                widget.destroy()
            self.on_success()
        else:
            self.status_label.config(text=f"激活失败: {msg}", foreground="red")
            messagebox.showerror("激活失败", msg)
