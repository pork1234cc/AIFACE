# -*- coding: utf-8 -*-
"""
单实例守卫核心实现

数据流（详见模块根目录 example.py）：

    acquire_single_instance(cfg)
        ↓
    第 1 次 CreateMutexW
        ├─ 不是 ERROR_ALREADY_EXISTS → 拿到锁，返回 True
        └─ ERROR_ALREADY_EXISTS（已有残留）
             ↓
        sys.frozen 且 kill_stale_in_frozen ?
             ├─ 否 → 返回 False（调用方走原弹窗）
             └─ 是
                  ↓
             taskkill /F /T /IM <exe> /FI "PID ne <self>"
                  ↓
             轮询重试 poll_retries × poll_interval
                  ├─ 拿到 → 返回 True
                  └─ 全失败 → 返回 False（调用方走原弹窗）

所有异常一律吞掉返回 False，绝不让单实例锁本身导致程序启动失败。
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import time
from typing import Optional, Tuple

from .config import SingleInstanceGuardConfig

logger = logging.getLogger("singleinstance_guard")
logger.addHandler(logging.NullHandler())   # 防止宿主未配置 handler 时报错

# Windows 错误码 & 子进程常量
_ERROR_ALREADY_EXISTS = 183
_CREATE_NO_WINDOW = 0x08000000

# 拿到的 Mutex 句柄必须持有到进程退出（Windows 通过句柄存活维持 Mutex 存活）
# 用模块级变量保留引用，避免被 GC 回收
_mutex_handle: Optional[int] = None


def _setup_kernel32():
    """配置 kernel32 的 argtypes/restype，避免 64 位上 HANDLE 被截断为 int32。"""
    k = ctypes.windll.kernel32
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    k.GetLastError.argtypes = []
    k.GetLastError.restype = ctypes.c_uint32
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.CloseHandle.restype = ctypes.c_bool
    return k


def _try_create_mutex(kernel32, mutex_name: str) -> Tuple[bool, Optional[int]]:
    """
    尝试创建一次 Mutex。

    Returns:
        (acquired, handle):
          - (True,  handle) → 拿到锁，handle 必须保留到进程退出
          - (False, None)   → 已存在，handle 已被 CloseHandle 关闭
    """
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()
    if last_error == _ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return False, None
    if not handle:
        # CreateMutexW 真的失败（极少见，比如名字非法）
        return False, None
    return True, handle


def _get_self_exe_name() -> Optional[str]:
    """打包态返回 EXE basename；开发态返回 python.exe 等（调用方会前置守卫）。"""
    try:
        name = os.path.basename(sys.executable)
        return name or None
    except Exception:
        return None


def _kill_stale_instance(exe_name: str, timeout: int) -> int:
    """
    调用 taskkill 清理同名残留进程，自动排除当前 PID。

    /F  强制结束（TerminateProcess，不发 WM_CLOSE）
    /T  连带杀子进程树（顺手带走 adb/uiautomator2 等残留子进程）
    /IM 按映像名匹配
    /FI "PID ne <self>"  关键过滤器，防止刚启动的新实例（同名 EXE）误杀自己

    Returns: taskkill 退出码（0=成功；非 0 不算异常，比如目标已自然退出）
    """
    cmd = [
        "taskkill", "/F", "/T",
        "/IM", exe_name,
        "/FI", f"PID ne {os.getpid()}",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    logger.info("已发送结束信号给残留进程: %s (rc=%s)", exe_name, result.returncode)
    return result.returncode


def acquire_single_instance(config: SingleInstanceGuardConfig) -> bool:
    """
    获取单实例锁。必须在 tk.Tk() 创建之前调用。

    检测到旧实例残留时，若打包态且 kill_stale_in_frozen=True，会自动
    taskkill 同名 EXE 残留进程并轮询重试。开发态不启用清理（防止
    python.exe 互相误杀）。

    Returns:
        True  - 已拿到锁，可继续启动主程序
        False - 真的有运行中的实例（或清理失败），调用方应弹窗并退出
    """
    global _mutex_handle

    # 已经拿到过锁，重复调用直接放行
    if _mutex_handle is not None:
        return True

    if os.name != "nt":
        logger.warning("singleinstance_guard 仅支持 Windows，非 NT 平台直接放行")
        return True

    try:
        kernel32 = _setup_kernel32()
    except Exception as e:
        logger.warning("无法加载 kernel32: %s，放行启动（不做单实例检查）", e)
        return True

    # 第一次尝试
    acquired, handle = _try_create_mutex(kernel32, config.mutex_name)
    if acquired:
        _mutex_handle = handle
        return True

    # 检测到残留，决定是否清理
    is_frozen = getattr(sys, "frozen", False)
    if not (is_frozen and config.kill_stale_in_frozen):
        # 开发态 / 用户禁用清理 → 走原行为（弹窗"程序已在运行"）
        return False

    exe_name = _get_self_exe_name()
    if not exe_name:
        logger.warning("拿不到自身 EXE 名，放弃清理，回退到弹窗")
        return False

    start = time.monotonic()
    try:
        _kill_stale_instance(exe_name, config.taskkill_timeout)
    except subprocess.TimeoutExpired:
        logger.warning("taskkill 超时（%ss），继续轮询 Mutex", config.taskkill_timeout)
    except Exception as e:
        logger.warning("taskkill 调用异常: %s，回退到弹窗", e)
        return False

    # 轮询重试：Mutex 在进程被 TerminateProcess 后不会立刻被内核回收
    for _ in range(config.poll_retries):
        time.sleep(config.poll_interval)
        acquired, handle = _try_create_mutex(kernel32, config.mutex_name)
        if acquired:
            _mutex_handle = handle
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info("旧实例已清理，本次启动继续（耗时 %d 毫秒）", elapsed)
            return True

    logger.warning("清理后仍无法获取单实例锁，回退到弹窗提示")
    return False
