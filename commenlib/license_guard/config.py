# -*- coding: utf-8 -*-
"""
license_guard 配置数据类

宿主项目通过 LicenseGuardConfig 注入所有外部依赖（服务器、路径、UI 文案等），
模块内部不再硬编码任何项目特定值。

Salt 拆分混淆（v_new 安全加固）：
  hmac_salt / machine_code_salt 的字符串字面值不出现在源码 / 编译产物中，
  改为运行时由两段无意义字节做 XOR 还原。IDA / strings 工具看到的只有
  乱码字节序列，无法 grep 出完整 salt。
"""
import os
import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlsplit


# ==================== Salt 拆分混淆 ====================
# 实际 salt 由 _XOR_SALT_A ^ _XOR_SALT_B 还原。两段独立字节序列单独看都是
# 随机字节，无法判断哪段对应哪个 salt，且无完整字符串可被 strings/IDA 抓取。
# 修改原则：一旦上线后不要轻易调整，否则会导致老用户凭证全部失效。

_HMAC_SALT_A = bytes([
    0xb1, 0x99, 0x8e, 0xb5, 0x62, 0x13, 0xce, 0xc0,
    0xe7, 0xd3, 0x2e, 0x3e, 0xbb, 0x4e, 0x7e, 0x41,
])
_HMAC_SALT_B = bytes([
    0xfd, 0xd0, 0xcd, 0xf0, 0x2c, 0x40, 0x8b, 0x9f,
    0xa0, 0x86, 0x6f, 0x6c, 0xff, 0x11, 0x28, 0x70,
])

_MCODE_SALT_A = bytes([
    0xfd, 0xd6, 0x74, 0x85, 0x04, 0x10, 0x26, 0x7d,
    0x03, 0x42, 0x05, 0x9b, 0xb0, 0xf4, 0x32, 0x73,
    0x8a, 0x47, 0x87,
])
_MCODE_SALT_B = bytes([
    0xa2, 0x9a, 0x3d, 0xc6, 0x41, 0x5e, 0x75, 0x38,
    0x5c, 0x05, 0x50, 0xda, 0xe2, 0xb0, 0x6d, 0x20,
    0xcb, 0x0b, 0xd3,
])


def _xor_salt(a: bytes, b: bytes) -> str:
    """XOR 还原 salt 原文。两段长度必须一致。"""
    return bytes(x ^ y for x, y in zip(a, b)).decode("utf-8")


# ==================== 配置数据类 ====================

@dataclass
class LicenseGuardConfig:
    # ---- 必填 ---- #
    server_url: str       # 激活服务端地址
    product_id: str       # 产品标识

    def __post_init__(self):
        if not isinstance(self.server_url, str):
            raise ValueError("license.server_url 必须为 HTTP(S) 地址")
        url = urlsplit(self.server_url)
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("license.server_url 必须为 HTTP(S) 地址")
        if not isinstance(self.product_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", self.product_id):
            raise ValueError("license.product_id 必须由英文字母、数字、下划线或连字符组成")
        if type(self.offline_grace_days) is not int or self.offline_grace_days < 0:
            raise ValueError("offline_grace_days 必须为非负整数")
        self.data_dir = os.path.join(os.environ["APPDATA"], self.product_id)

    # ---- UI 定制 ---- #
    app_title: str = "软件激活"
    app_heading: str = "软件激活"
    code_hint: str = "XXXX-XXXX-XXXX-XXXX"
    window_width: int = 500
    window_height: int = 300

    # ---- 行为调优 ---- #
    offline_grace_days: int = 7
    max_retries: int = 2
    retry_delay: float = 1.5
    cmd_timeout: int = 10

    # ---- 安全（salt 拆分混淆，运行时 XOR 还原原值） ---- #
    hmac_salt: str = field(default_factory=lambda: _xor_salt(_HMAC_SALT_A, _HMAC_SALT_B))
    machine_code_salt: str = field(default_factory=lambda: _xor_salt(_MCODE_SALT_A, _MCODE_SALT_B))

    # ---- 旧版迁移 ---- #
    # 仅在需要兼容旧版安装目录时填写，否则保持默认空列表即可。
    # 场景：产品改名/改路径后，自动将旧凭证迁移到新目录，避免用户重新激活。
    legacy_dirs: List[str] = field(default_factory=list)              # 旧版数据目录路径列表
    legacy_license_names: List[str] = field(default_factory=lambda: ["license.dat", "license.json"])       # 旧版激活文件名
    legacy_machine_id_names: List[str] = field(default_factory=lambda: ["machine_id.dat", ".machine_id"])  # 旧版机器码文件名

    # ---- 派生路径 ---- #
    @property
    def machine_id_path(self) -> str:
        return os.path.join(self.data_dir, "machine_id.dat")

    @property
    def license_path(self) -> str:
        return os.path.join(self.data_dir, "license.dat")
