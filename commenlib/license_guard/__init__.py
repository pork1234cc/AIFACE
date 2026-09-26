# -*- coding: utf-8 -*-
"""
license_guard - 可复用的软件激活与验证模块

平台要求：仅支持 Windows（机器码采集依赖 PowerShell/WMIC 查询硬件信息）

使用方式:
    from license_guard import LicenseGuardConfig, LicenseClient, LicenseGUI

    config = LicenseGuardConfig(
        server_url="https://your-server.com",
        product_id="your_product",
    )
    client = LicenseClient(config)
    ok, msg, info = client.verify()
"""
from .config import LicenseGuardConfig
from .license_client import LicenseClient
from .machine_code import get_machine_code
from .auth_window import LicenseGUI
from .tk_helper import show_license_info_tk, start_periodic_verify

__all__ = [
    "LicenseGuardConfig",
    "LicenseClient",
    "LicenseGUI",
    "get_machine_code",
    "show_license_info_tk",
    "start_periodic_verify",
]
