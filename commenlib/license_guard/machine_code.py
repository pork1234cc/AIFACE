# -*- coding: utf-8 -*-
"""
机器码生成模块

基于硬件因子生成唯一安装标识符，首次生成后持久化到磁盘。

首次生成因子：
1. 主板UUID   Win32_ComputerSystemProduct.UUID
2. CPU处理器ID Win32_Processor.ProcessorId
3. BIOS序列号  Win32_BIOS.SerialNumber

获取方式：PowerShell (推荐) -> WMIC (降级)
"""
import os
import re
import subprocess
import hashlib
import platform
import logging
import sys
from typing import Optional

from .config import LicenseGuardConfig

logger = logging.getLogger(__name__)

# 模块级缓存，避免重复调用
_cache: Optional[str] = None

# 无效硬件值黑名单
_INVALID_VALUES = {
    "to be filled", "to be filled by o.e.m.",
    "default string", "none", "n/a", "not available",
    "00000000", "ffffffff",
    "system manufacturer", "system product name",
}

# 持久化文件中合法机器码的正则
_CODE_PATTERN = re.compile(r"^[0-9A-F]{32}$")


# ==================== 公共 API ====================

def get_machine_code(config: LicenseGuardConfig) -> str:
    """
    获取本机机器码（32位大写MD5）

    流程：
    1. 内存缓存 -> 有则直接返回
    2. 磁盘持久化文件 -> 有有效code则直接返回（不采集硬件）
    3. 无持久化 -> 采集硬件因子 -> 计算MD5 -> 持久化 -> 返回
    """
    global _cache
    if _cache is not None:
        return _cache

    # 尝试从磁盘读取已持久化的机器码
    saved_code = _load_machine_id(config)
    if saved_code:
        _cache = saved_code
        logger.info("机器码已从持久化文件加载")
        return _cache

    # 无持久化记录，首次生成
    factors = _collect_factors(config.cmd_timeout)
    valid_count = len([f for f in factors if f])
    _cache = _compute_code(factors, config.machine_code_salt)
    _save_machine_id(config, _cache)
    logger.info(f"机器码首次生成并持久化（因子数: {valid_count}/3）")
    return _cache


def override_machine_code(config: LicenseGuardConfig, code: str):
    """
    强制将机器码覆盖为指定值并持久化。
    用于旧版迁移：旧凭证中的机器码是服务端已绑定的，必须沿用。
    """
    global _cache
    _cache = code
    _save_machine_id(config, code)
    logger.info("机器码已被旧版迁移覆盖并持久化")


def get_fresh_machine_code(config: LicenseGuardConfig) -> str:
    """
    绕过所有缓存，直接采集硬件因子计算机器码。
    用于安全验证路径（HMAC 密钥派生）。
    """
    factors = _collect_factors(config.cmd_timeout)
    return _compute_code(factors, config.machine_code_salt)


# ==================== 因子采集 ====================

def _collect_factors(cmd_timeout: int) -> list:
    """
    采集固定3个硬件因子，始终返回长度为3的列表。
    获取失败的因子用空字符串占位，保证结构固定。
    3个查询并行执行以减少启动耗时。
    """
    from concurrent.futures import ThreadPoolExecutor

    args = [
        ("csproduct", "UUID", "Win32_ComputerSystemProduct", "UUID", cmd_timeout),
        ("cpu", "ProcessorId", "Win32_Processor", "ProcessorId", cmd_timeout),
        ("bios", "SerialNumber", "Win32_BIOS", "SerialNumber", cmd_timeout),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_get_hw_value, *a) for a in args]
        return [f.result() for f in futures]


def _compute_code(factors: list, salt: str) -> str:
    """根据因子列表计算机器码"""
    labeled = [
        f"BOARD:{factors[0]}",
        f"CPU:{factors[1]}",
        f"BIOS:{factors[2]}",
    ]
    labeled.sort()
    combined = "|".join(labeled)
    salted = combined + salt
    return hashlib.md5(salted.encode("utf-8")).hexdigest().upper()


# ==================== 硬件信息获取 ====================

def _get_hw_value(wmic_class: str, wmic_field: str,
                  cim_class: str, cim_property: str,
                  cmd_timeout: int) -> str:
    """获取硬件属性值：PowerShell 优先，WMIC 降级"""
    if platform.system() != "Windows":
        return ""

    value = _powershell_get(cim_class, cim_property, cmd_timeout)
    if value:
        return value

    value = _wmic_get(wmic_class, wmic_field, cmd_timeout)
    if value:
        return value

    return ""


def _powershell_get(cim_class: str, cim_property: str, timeout: int) -> str:
    """通过 PowerShell Get-CimInstance 获取硬件信息"""
    try:
        cmd = (
            f'powershell -NoProfile -Command '
            f'"(Get-CimInstance {cim_class}).{cim_property}"'
        )
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, shell=True,
            startupinfo=_get_startupinfo(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        value = result.stdout.strip()
        if _is_valid(value):
            return value
    except Exception as e:
        logger.debug(f"PowerShell {cim_class}.{cim_property} 失败: {e}")
    return ""


def _wmic_get(category: str, field: str, timeout: int) -> str:
    """通过 WMIC 获取硬件信息（降级方案）"""
    try:
        cmd = f"wmic {category} get {field}"
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, shell=True,
            startupinfo=_get_startupinfo(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            value = lines[1].strip()
            if _is_valid(value):
                return value
    except Exception as e:
        logger.debug(f"WMIC {category}.{field} 失败: {e}")
    return ""


# ==================== 持久化 ====================

def _load_machine_id(config: LicenseGuardConfig) -> str:
    """
    从磁盘读取机器码。
    兼容旧版JSON格式和纯字符串格式。
    """
    path = config.machine_id_path
    code = _read_code_from_file(path)
    if code:
        return code

    # 旧版迁移：检查 config.legacy_dirs 中的旧路径
    legacy_paths = _get_legacy_paths(config)
    for lp in legacy_paths:
        code = _read_code_from_file(lp)
        if code:
            logger.info(f"从旧路径迁移机器码: {lp} -> {path}")
            _save_machine_id(config, code)
            _try_remove(lp)
            return code

    return ""


def _read_code_from_file(path: str) -> str:
    """从单个文件读取机器码"""
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return ""

        # 兼容旧版JSON格式 {"code": "...", ...}
        if content.startswith("{"):
            import json
            data = json.loads(content)
            code = data.get("code", "")
            if _CODE_PATTERN.match(code):
                return code
        # 纯32位字符串格式
        elif _CODE_PATTERN.match(content):
            return content
    except Exception as e:
        logger.debug(f"读取机器码失败 ({path}): {e}")
    return ""


def _save_machine_id(config: LicenseGuardConfig, code: str):
    """将机器码写入持久化文件"""
    path = config.machine_id_path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"保存机器码失败 ({path}): {e}")


def _get_legacy_paths(config: LicenseGuardConfig) -> list:
    """从 config.legacy_dirs 获取旧版可能存在的机器码文件路径"""
    paths = []
    for d in config.legacy_dirs:
        for name in config.legacy_machine_id_names:
            p = os.path.join(d, name)
            if os.path.exists(p):
                paths.append(p)
    return paths


def _try_remove(path: str):
    """尝试删除文件，失败时静默"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ==================== 工具函数 ====================

def _is_valid(value: str) -> bool:
    """检查硬件值是否有效（排除已知无效值）"""
    if not value or len(value) < 4:
        return False
    return value.lower().strip() not in _INVALID_VALUES


def _get_startupinfo():
    """Windows 下隐藏子进程窗口"""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        return si
    return None
