# -*- coding: utf-8 -*-
"""
update_guard 配置数据类

宿主项目通过 UpdateGuardConfig 注入所有外部依赖（检查地址、版本号等），
模块内部不硬编码任何项目特定值。
"""
from dataclasses import dataclass


@dataclass
class UpdateGuardConfig:
    # ---- 必填 ---- #
    check_url: str          # version.json 远程地址
    current_version: str    # 当前版本号，如 "1.1"

    # ---- 行为调优 ---- #
    timeout: int = 10       # HTTP 请求超时（秒）

    # ---- JSON 字段名映射（适配不同服务端 schema） ---- #
    field_latest_version: str = "latest_version"
    field_download_url: str = "download_url"
    field_changelog: str = "changelog"
