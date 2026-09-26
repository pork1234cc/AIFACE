# -*- coding: utf-8 -*-
"""
激活码验证客户端

验证流程:
  启动 -> 联网验证
       |-- 成功 -> 本地记录 {last_verify: now}
       +-- 失败(网络) -> 检查 last_verify
                         |-- < grace_days -> 宽限通过
                         +-- >= grace_days -> 拒绝
       +-- 失败(服务端拒绝) -> 直接拒绝

本地存储：HMAC 签名信封 JSON，凭证只存用户目录。
"""
import os
import json
import hmac
import hashlib
import logging
import time
import requests
from datetime import datetime, timedelta
from typing import Tuple, Dict

from .config import LicenseGuardConfig
from .machine_code import get_machine_code

logger = logging.getLogger(__name__)

# 创建不走系统代理的 Session（防止 VPN/代理导致连接超时）
_session = requests.Session()
_session.trust_env = False

_HMAC_VERSION = "v1"


def _retry_request(method: str, url: str,
                   max_retries: int, retry_delay: float,
                   **kwargs) -> requests.Response:
    """带重试的 HTTP 请求"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            func = _session.get if method == "get" else _session.post
            return func(url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
    raise last_error


def _normalize_expire(expire_raw: str) -> str:
    """统一到期时间格式"""
    if expire_raw == "永久":
        return "9999-12-31 23:59:59"
    return expire_raw


class LicenseClient:
    """
    激活码客户端

    凭证存储到 config.data_dir（用户目录），使用 HMAC 签名防篡改。
    """

    def __init__(self, config: LicenseGuardConfig):
        self.config = config
        self.server_url = config.server_url.rstrip("/")
        self.machine_code = get_machine_code(config)

        self._path = config.license_path
        # cred_version 在 _load_single 内部从 envelope.cred_version 拿到用于派生密钥；
        # 加载完成后 self.cred_version 从 _cache 取出，供 verify 请求体上送服务端
        self._cache = self._load()
        # 服务端下发的凭证版本号：activate / verify 成功时由服务端返回，
        # 客户端持久化后作为 HMAC 派生因子 + verify 请求体上送
        # 空串：老用户从 v_old 升级 / 首次启动未激活 → 等效旧算法，HMAC 派生与 v_old 一致
        self.cred_version: str = self._cache.get("cred_version", "")

    # ==================== HMAC ====================

    # 服务端响应时间戳新鲜度阈值（防重放）：±5 分钟
    _RESPONSE_TS_TOLERANCE_SECONDS = 300

    def _verify_response_sig(self, resp_data: dict, code: str) -> Tuple[bool, str]:
        """
        校验服务端响应签名 + 时间戳新鲜度（防中间人篡改 / 假服务器 / 重放）。

        协议：服务端响应应包含 ``ts / nonce / sig`` 三字段，其中
            sig = HMAC_SHA256(
                key   = activate_code,
                msg   = "{success}|{expire_date}|{card_type}|{revoked}|{nonce}|{ts}"
            )
        以 ``code`` 作为 HMAC 密钥源：反编译拿不到（不在源码 / 不在配置）。

        兼容期：响应不含 sig 字段时打 warning 仍接受，过渡 1 个版本后强制要求。

        Returns:
            (ok, error_msg) ok=True 表示验签通过或处于兼容期；False 表示拒绝
        """
        if "sig" not in resp_data:
            logger.warning("服务端响应缺少 sig 字段，兼容期内仍接受；下一版将强制要求验签")
            return True, ""

        nonce = str(resp_data.get("nonce", ""))
        ts_raw = resp_data.get("ts", 0)
        sig = str(resp_data.get("sig", ""))

        try:
            ts_int = int(ts_raw)
        except (TypeError, ValueError):
            return False, "服务端响应 ts 字段无效"

        now = int(time.time())
        if abs(now - ts_int) > self._RESPONSE_TS_TOLERANCE_SECONDS:
            return False, f"服务端响应时间戳异常（偏差 {abs(now - ts_int)}s，超出允许范围）"

        # 统一布尔值表示：true/false（与服务端协议保持小写）
        success = str(resp_data.get("success", "")).lower()
        expire_date = str(resp_data.get("expire_date", ""))
        card_type = str(resp_data.get("card_type", ""))
        revoked = str(resp_data.get("revoked", False)).lower()

        msg = f"{success}|{expire_date}|{card_type}|{revoked}|{nonce}|{ts_int}"
        expected = hmac.new(
            code.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, sig):
            return False, "服务端响应签名不匹配（可能被中间人篡改或来自假服务器）"

        return True, ""

    def _hmac_key(self, cred_version: str | None = None) -> bytes:
        """
        派生 HMAC 密钥。

        密钥源 = machine_code + cred_version + hmac_salt
        其中 cred_version 由服务端 activate / verify 响应下发并保存在本地，
        它用于服务端撤销校验，不是客户端无法读取的秘密；
        cred_version 为空串时等同 v_old 算法（向后兼容老凭证）。

        Args:
            cred_version: None 则使用 self.cred_version；
                显式传入字符串可强制用指定值派生（用于 _load_single 内部
                从 envelope.cred_version 还原密钥时——避免 chicken-and-egg：
                self.cred_version 在 _load 完成前还是空）。
        """
        cv = self.cred_version if cred_version is None else cred_version
        return hashlib.sha256(
            (self.machine_code + cv + self.config.hmac_salt).encode("utf-8")
        ).digest()

    # ==================== 本地过期检查 ====================

    def _is_locally_expired(self) -> bool:
        expire_str = self._cache.get("expire_time", "").strip()
        if not expire_str:
            return False
        if expire_str == "9999-12-31 23:59:59":
            return False
        try:
            expire_dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
            return datetime.now() > expire_dt
        except ValueError:
            try:
                expire_dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M")
                return datetime.now() > expire_dt
            except ValueError:
                return False

    def _is_time_rollback(self) -> bool:
        # 永久卡不检测
        expire_str = self._cache.get("expire_time", "").strip()
        if expire_str == "9999-12-31 23:59:59":
            return False

        last_seen = self._cache.get("last_seen_time", "")
        if not last_seen:
            return False

        try:
            last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            from datetime import timedelta
            # v_new 收紧：阈值由 5 分钟降至 60 秒，2 分钟的时间回拨即可检测到
            if now < last_seen_dt - timedelta(seconds=60):
                return True
        except ValueError:
            pass
        return False

    def _update_last_seen(self):
        self._cache["last_seen_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()

    # ==================== 对外接口 ====================

    def is_activated(self) -> bool:
        return bool(self._cache.get("code"))

    def get_cache_info(self) -> dict:
        return dict(self._cache)

    def activate(self, code: str) -> Tuple[bool, str, Dict]:
        code = code.strip().upper()
        if not code:
            return False, "请输入激活码", {}

        try:
            resp = _retry_request(
                "post",
                f"{self.server_url}/activate",
                self.config.max_retries, self.config.retry_delay,
                json={"code": code, "machine_code": self.machine_code,
                      "product": self.config.product_id},
                timeout=15,
            )
            data = resp.json()

            # 响应验签：activate 时用请求体里发的 code（用户输入）作 HMAC 密钥
            sig_ok, sig_err = self._verify_response_sig(data, code)
            if not sig_ok:
                logger.warning(f"activate 响应验签失败: {sig_err}")
                return False, f"服务端响应异常：{sig_err}", {}

            ok = data.get("success", False)
            msg = data.get("message", "")
            expire_time = _normalize_expire(data.get("expire_date", ""))
            card_type = data.get("card_type", "")
            # 服务端首次激活 / 解绑重激活会生成新的 cred_version 并下发
            srv_cred_version = str(data.get("cred_version", "")).strip()

            normalized = {
                "expire_time": expire_time,
                "card_type": card_type,
            }

            if ok:
                # 激活成功 → 持久化服务端下发的 cred_version 作为后续 HMAC 派生因子
                self.cred_version = srv_cred_version
                self._cache = {
                    "code": code,
                    "machine_code": self.machine_code,
                    "cred_version": self.cred_version,
                    "expire_time": expire_time,
                    "card_type": card_type,
                    "last_verify": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self._save()
                return True, msg or "激活成功", normalized

            return False, msg or "激活失败", normalized

        except requests.ConnectionError:
            return False, "无法连接服务器，请检查网络", {}
        except requests.Timeout:
            return False, "服务器响应超时", {}
        except Exception as e:
            return False, f"激活异常: {e}", {}

    def verify(self) -> Tuple[bool, str, Dict]:
        if not self._cache.get("code"):
            return False, "未激活", {}

        code = self._cache["code"]

        if self._cache.get("machine_code") != self.machine_code:
            self._clear()
            return False, "激活信息与本机不匹配", {}

        if self._is_locally_expired():
            expire_time = self._cache.get("expire_time", "")
            self._clear()
            return False, f"授权已过期({expire_time})", {"expire_time": expire_time}

        if self._is_time_rollback():
            logger.warning("检测到系统时间回拨")
            return False, "系统时间异常，请校准后重试", {}

        try:
            resp = _retry_request(
                "post",
                f"{self.server_url}/verify",
                self.config.max_retries, self.config.retry_delay,
                json={"code": code, "machine_code": self.machine_code,
                      "cred_version": self.cred_version,
                      "product": self.config.product_id},
                timeout=5,
            )
            if resp.status_code >= 500:
                logger.warning(f"服务端错误 HTTP {resp.status_code}，走离线宽限")
                return self._grace_verify()
            data = resp.json()

            # 响应验签：verify 时用本地缓存的 code 作 HMAC 密钥
            sig_ok, sig_err = self._verify_response_sig(data, code)
            if not sig_ok:
                logger.warning(f"verify 响应验签失败: {sig_err}")
                return False, f"服务端响应异常：{sig_err}", {}

            # 服务端主动撤销（revoked 字段已纳入响应签名，不可被中间人伪造）
            if data.get("revoked", False):
                logger.warning("授权已被服务端撤销")
                self._clear()
                return False, data.get("message") or "授权已被服务端撤销", {"revoked": True}

            ok = data.get("success", False)

            # 服务端 cred_version 不匹配（凭证被移植 / 管理员撤销）
            # 服务端返回：HTTP 403 + {success: false, code: "INVALID_CRED_VERSION", message: ...}
            err_code = str(data.get("code", ""))
            if err_code == "INVALID_CRED_VERSION":
                logger.warning(f"凭证版本失效（服务端撤销或被移植）: {data.get('message')}")
                self._clear()
                return False, data.get("message") or "凭证已失效，请重新激活", {
                    "code": "INVALID_CRED_VERSION",
                }

            if ok:
                expire_time = _normalize_expire(data.get("expire_date", ""))
                card_type = data.get("card_type", "")
                srv_cred_version = str(data.get("cred_version", "")).strip()

                # 升级老用户：首次成功 verify 时服务端会下发 cred_version
                # 本地落地后下次 _save 用新算法签名，下次启动直接走 v_new 路径
                if srv_cred_version and srv_cred_version != self.cred_version:
                    logger.info("从服务端更新 cred_version（首次升级或服务端续签）")
                    self.cred_version = srv_cred_version

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._cache["expire_time"] = expire_time or self._cache.get("expire_time", "")
                self._cache["card_type"] = card_type or self._cache.get("card_type", "")
                self._cache["cred_version"] = self.cred_version
                self._cache["last_verify"] = now_str
                self._cache["last_seen_time"] = now_str
                self._save()

                if self._is_locally_expired():
                    self._clear()
                    return False, f"授权已过期({expire_time})", {"expire_time": expire_time}

                return True, "验证通过", {
                    "expire_time": expire_time,
                    "card_type": card_type,
                }

            self._clear()
            return False, data.get("message", "验证失败"), data

        except (requests.ConnectionError, requests.Timeout):
            return self._grace_verify()
        except Exception as e:
            logger.error(f"验证异常: {e}")
            return False, "授权验证响应异常，请重试或联系管理员", {}

    # ==================== 离线宽限 ====================

    def _grace_verify(self) -> Tuple[bool, str, Dict]:
        if self._is_locally_expired():
            expire_time = self._cache.get("expire_time", "")
            self._clear()
            return False, f"授权已过期({expire_time})", {"expire_time": expire_time}

        if self._is_time_rollback():
            logger.warning("离线宽限期内检测到系统时间回拨")
            return False, "系统时间异常，请校准后联网验证", {}

        card_type = self._cache.get("card_type", "")
        if card_type == "试用卡":
            logger.warning("试用卡离线宽限被拒绝")
            return False, "试用卡需要联网验证，请检查网络连接", {}

        # 永久卡也禁离线宽限（v_new 安全加固）：
        # v_old 永久卡走"过期检查跳过"→ 攻击者伪造永久卡凭证可在离线环境无限使用
        # v_new 永久卡必须联网验证，与试用卡同等待遇
        expire_time = self._cache.get("expire_time", "").strip()
        if expire_time == "9999-12-31 23:59:59":
            logger.warning("永久卡离线宽限被拒绝（v_new 安全策略）")
            return False, "永久卡需要联网验证，请检查网络连接", {}

        last_verify = self._cache.get("last_verify", "")
        if not last_verify:
            return False, "无验证记录，请联网验证", {}

        try:
            last_dt = datetime.strptime(last_verify, "%Y-%m-%d %H:%M:%S")
            elapsed = datetime.now() - last_dt
            if elapsed < timedelta(0):
                return False, "系统时间异常，请校准后联网验证", {}
            if elapsed < timedelta(days=self.config.offline_grace_days):
                self._update_last_seen()
                return True, f"离线验证通过(宽限期内，已离线{elapsed.days}天)", {}
            return False, f"已离线超过{self.config.offline_grace_days}天，请联网验证", {}
        except ValueError:
            return False, "本地缓存异常，请联网验证", {}

    # ==================== 存储（HMAC 签名） ====================

    def _load(self) -> dict:
        """加载凭证，优先新路径，兼容旧路径迁移"""
        data = self._load_single(self._path)
        if data or os.path.exists(self._path):
            # 新路径存在即为权威状态，不能用旧副本恢复撤销或损坏的凭证。
            return data

        # 旧版迁移
        for lp in self._get_legacy_paths():
            data = self._load_legacy(lp)
            if data:
                logger.info(f"从旧路径迁移激活信息: {lp}")
                # 仅迁移使用当前机器码验签成功的凭证，不由凭证覆盖机器码。
                self._cache = data
                self._save()
                # 保留旧文件，避免写入失败时丢失唯一副本。
                return data

        return {}

    def _save(self):
        """保存凭证到用户目录（HMAC 签名）"""
        self._save_single(self._path, self._cache)

    def _clear(self):
        """清除凭证内容，保留空状态以阻止旧路径再次迁移。"""
        self._cache = {}
        self.cred_version = ""
        self._save()

    def _save_single(self, path: str, data: dict):
        """
        保存 HMAC 签名信封到文件。

        envelope 明文存 cred_version 用于解决 chicken-and-egg：
        加载时还没有 self.cred_version，需要从 envelope 里读出来才能派生密钥。
        cred_version 同时纳入 HMAC 派生 → 攻击者改 envelope.cred_version
        会让签名密钥变化，签名校验失败。
        """
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            cv = data.get("cred_version", "")
            signature = hmac.new(
                self._hmac_key(cred_version=cv),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            envelope = json.dumps({
                "hmac_version": _HMAC_VERSION,
                "cred_version": cv,
                "signature": signature,
                "data": payload,
            }, ensure_ascii=False)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(envelope)
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"保存缓存失败 ({path}): {e}")

    def _load_single(self, path: str) -> dict:
        """
        从文件加载并验证 HMAC。

        从 envelope.cred_version 还原 HMAC 派生密钥：
        - v_old 凭证：envelope 无 cred_version 字段，``.get("", "")`` 返回 ""
          → 派生密钥与 v_old 完全一致 → 老凭证自然兼容
        - v_new 凭证：envelope.cred_version = 服务端下发值 → 派生密钥含此值
          → 移植到他机：machine_code 不同 → 派生密钥不同 → 签名校验失败
          → 单字段被篡改 envelope.cred_version：密钥变化 → 签名校验失败
        """
        try:
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return {}
            raw = json.loads(content)

            if not isinstance(raw, dict):
                return {}

            # HMAC 签名信封格式
            if "signature" in raw and "data" in raw:
                envelope_cv = str(raw.get("cred_version", ""))
                payload = raw["data"]
                signature = raw["signature"]

                expected = hmac.new(
                    self._hmac_key(cred_version=envelope_cv),
                    payload.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(expected, signature):
                    data = json.loads(payload)
                    if not isinstance(data, dict):
                        return {}
                    fields = ("code", "machine_code", "cred_version", "expire_time",
                              "card_type", "last_verify", "last_seen_time")
                    if any(not isinstance(data.get(key, ""), str) for key in fields):
                        return {}
                    if not data.get("code") or data.get("machine_code") != self.machine_code:
                        return {}
                    if data.get("cred_version", "") != envelope_cv:
                        return {}
                    return data

                logger.warning(f"HMAC校验失败 ({path})，凭证可能已被篡改或从其他机器复制")
                return {}

            logger.warning("旧凭证缺少有效签名，请重新联网激活: %s", path)
            return {}
        except Exception as e:
            logger.debug(f"读取缓存失败 ({path}): {e}")
            return {}

    def _load_legacy(self, path: str) -> dict:
        """旧路径与新路径使用同一验签规则；无签名旧凭证需重新激活。"""
        return self._load_single(path)

    def _get_legacy_paths(self) -> list:
        """从 config.legacy_dirs 获取旧版凭证文件路径"""
        paths = []
        for d in self.config.legacy_dirs:
            for name in self.config.legacy_license_names:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    paths.append(p)
        return paths
