# -*- coding: utf-8 -*-
"""
commenlib - 通用模块包（激活验证 + 自动更新 + 单实例锁 + 编译打包）

宿主项目接入方式（仅需 3 步）：

  1. 把本目录整体拷贝到宿主项目下，命名为 ``commenlib/``
  2. 复制 ``commenlib/_template/project.yaml`` 到宿主项目根目录，填字段
  3. 在 ``main.py`` 中：

        from commenlib import AppInit

        def main():
            app = AppInit()
            root = tk.Tk()
            root.withdraw()

            def on_license_ok():
                launch_main_app(root, app)
                app.start_periodic_verify(root)

            app.verify_license_async(root, on_license_ok)
            root.mainloop()

打包：``python commenlib/buildsystem/build_all.py``
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

import yaml

__all__ = ["AppInit"]


def _find_project_yaml() -> Path:
    """
    定位宿主项目根目录下的 project.yaml。

    - 开发态：``__file__`` 指向 ``<宿主根>/commenlib/__init__.py``，
      上溯一层即宿主根。
    - 冻结态（PyInstaller）：``sys._MEIPASS`` 为运行时解压目录，
      ``project.yaml`` 通过 build.spec 打入该目录根（参见 build.spec 的 DATAS）。
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "project.yaml"
    # __file__ = <宿主根>/commenlib/__init__.py → parent.parent = 宿主根
    # 用 absolute() 而非 resolve()：resolve 会展开符号链接/junction，
    # 在 commenlib 通过 git submodule 或目录 junction 接入时会指向真实仓库位置而非宿主根
    return Path(__file__).absolute().parent.parent / "project.yaml"


def _load_yaml() -> dict:
    cfg_path = _find_project_yaml()
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"找不到配置文件：{cfg_path}\n"
            "请将 commenlib/_template/project.yaml 复制到宿主项目根目录并填写配置。"
        )
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class AppInit:
    """
    读取 project.yaml，提供统一的应用信息访问和异步授权/更新接口。

    属性：
        name            str  - 软件名称（来自 app.name）
        version         str  - 版本号（来自 app.version）
        license_client       - LicenseClient 实例（授权通过后可用，未激活时为 None）

    方法：
        verify_license_async(root, on_success)  异步验证授权，通过后回调 on_success
        start_periodic_verify(widget)           启动后台定期授权验证（每 24h）
        check_update_async(widget)              手动触发后台检查更新 + UI 弹窗
        show_license_info(widget)               弹窗展示当前授权状态
    """

    def __init__(self) -> None:
        cfg = _load_yaml()

        app_cfg = cfg.get("app", {})
        self.name: str = app_cfg.get("name", "App")
        self.version: str = str(app_cfg.get("version", "1.0.0"))

        self._license_cfg_raw: dict = cfg.get("license", {})
        self._update_cfg_raw: dict = cfg.get("update", {})

        self._license_config = self._build_license_config()
        self._update_config = self._build_update_config()

        self.license_client = None

    # ------------------------------------------------------------------
    def _build_license_config(self):
        from .license_guard import LicenseGuardConfig

        kwargs = {
            "server_url": self._license_cfg_raw.get("server_url", ""),
            "product_id": self._license_cfg_raw.get("product_id", ""),
            "app_title": self._license_cfg_raw.get("app_title", f"{self.name} 激活"),
            "app_heading": self._license_cfg_raw.get("app_heading", self.name),
        }
        if self._license_cfg_raw.get("offline_grace_days") is not None:
            kwargs["offline_grace_days"] = self._license_cfg_raw["offline_grace_days"]
        return LicenseGuardConfig(**kwargs)

    def _build_update_config(self):
        try:
            from .update_guard import UpdateGuardConfig
        except ImportError:
            return None

        kwargs = {
            "check_url": self._update_cfg_raw.get("check_url", ""),
            "current_version": self.version,
        }
        if self._update_cfg_raw.get("timeout") is not None:
            kwargs["timeout"] = self._update_cfg_raw["timeout"]
        return UpdateGuardConfig(**kwargs)

    # ------------------------------------------------------------------
    def verify_license_async(
        self,
        root: tk.Tk,
        on_success: Callable[[], None],
        on_fail: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        后台异步验证授权。

        流程：
          1. 后台线程中读取本地凭证并验证
          2. 若已激活且验证通过 → 主线程回调 on_success
          3. 若未激活或验证失败 → 主线程弹出激活窗口（LicenseGUI），
             激活成功后回调 on_success；用户关闭窗口则进程退出

        Args:
            root: Tkinter 根窗口（用于 after 调度 + 作为激活窗父窗口）
            on_success: 授权通过后的回调（主线程调用）
            on_fail: 可选，后台验证失败时的日志回调（主线程调用，消息为字符串）
        """
        if self._license_config is None:
            raise RuntimeError("授权配置不可用，不能跳过授权验证")

        from .license_guard import LicenseClient

        def _worker():
            client = LicenseClient(self._license_config)
            if client.is_activated():
                ok, msg, _ = client.verify()
                if ok:
                    self.license_client = client
                    root.after(0, on_success)
                    return
                if on_fail:
                    root.after(0, lambda m=msg: on_fail(m))
            else:
                if on_fail:
                    root.after(0, lambda: on_fail("未激活"))

            root.after(0, lambda: self._show_activation_window(root, client, on_success))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_activation_window(self, root: tk.Tk, client, on_success: Callable[[], None]) -> None:
        from .license_guard import LicenseGUI

        def _on_activated():
            self.license_client = client
            on_success()

        LicenseGUI(root, on_success=_on_activated, config=self._license_config, client=client)
        root.deiconify()

    # ------------------------------------------------------------------
    def start_periodic_verify(self, widget: tk.Widget) -> None:
        """
        启动后台定期授权验证（每 24 小时联网验证一次）。
        需在授权通过后调用，永久卡同样参与验证。
        """
        if self.license_client is None:
            return
        from .license_guard import start_periodic_verify
        start_periodic_verify(widget, self.license_client)

    # ------------------------------------------------------------------
    def check_update_async(self, widget: tk.Widget) -> None:
        """
        手动触发后台检查更新。

        调用后立即返回，在后台线程发起 HTTP 请求，完成后在主线程弹窗：
          - 有更新 → 提示版本号 + 更新内容 + 询问是否打开下载页
          - 无更新 → 提示已是最新版
          - 网络错误 → 提示无法连接更新服务器
        """
        if self._update_config is None:
            return
        try:
            from .update_guard import check_update_tk
        except ImportError:
            return
        check_update_tk(widget, self._update_config)

    # ------------------------------------------------------------------
    def show_license_info(self, widget: tk.Widget) -> None:
        """弹窗展示当前授权状态（机器码、卡类型、到期时间等）"""
        if self.license_client is None:
            try:
                from .license_guard import LicenseClient
                client = LicenseClient(self._license_config)
            except ImportError:
                return
        else:
            client = self.license_client

        try:
            from .license_guard import show_license_info_tk
        except ImportError:
            return
        show_license_info_tk(widget, client)
