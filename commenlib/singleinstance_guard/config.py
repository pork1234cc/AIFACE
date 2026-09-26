# -*- coding: utf-8 -*-
"""
singleinstance_guard 配置数据类

宿主项目通过 SingleInstanceGuardConfig 注入 Mutex 名与行为参数，
模块内部不硬编码任何项目特定值。
"""
from dataclasses import dataclass


@dataclass
class SingleInstanceGuardConfig:
    # ---- 必填 ---- #
    mutex_name: str          # Windows Mutex 全局名，如 r"Global\YourApp_SingleInstance"

    # ---- 行为调优 ---- #
    # 默认不结束已有进程；无法仅凭 Mutex 区分正常实例与残留实例。
    # 显式开启后，打包态会按 EXE 名强制结束其他同名进程及其子进程。
    # 开发态（python.exe）永远不启用，避免误杀其他 Python 进程。
    kill_stale_in_frozen: bool = False

    # taskkill 后轮询 Mutex 的次数（Mutex 在进程被 TerminateProcess 后不会立刻释放）
    poll_retries: int = 5
    # 每次轮询间隔（秒）。默认 5×0.2 = 1 秒总时长
    poll_interval: float = 0.2
    # taskkill 子进程超时（秒）
    taskkill_timeout: int = 5
