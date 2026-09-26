"""网页宿主的授权运行时；同步客户端串行运行，不调用 Tk 辅助函数。"""

import logging
import time
from datetime import datetime, timedelta
from threading import RLock

import httpx
import yaml

from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


def safe_failure_message(message):
    """将组件错误映射为固定提示，不回显可能包含卡密或地址的原始响应。"""
    if not isinstance(message, str):
        return "授权未通过，请检查卡密、有效期或网络后重试"
    if any(term in message for term in ("Expecting value", "Extra data", "JSONDecodeError")):
        return "授权服务返回格式错误，请核对授权 HTTP 地址；当前无法判断卡密是否有效"
    if "超时" in message:
        return "授权服务器响应超时，请稍后重试"
    if "无法连接服务器" in message:
        return "无法连接授权服务器，请检查网络和授权服务地址"
    if "过期" in message:
        return "授权已过期，请核对卡密有效期"
    if any(term in message for term in ("撤销", "停用", "封禁")):
        return "授权已被停用，请联系发卡方核对"
    if any(term in message for term in ("已绑定", "本机不匹配", "其他设备")):
        return "卡密绑定信息与本机不符，请联系发卡方核对"
    if any(term in message for term in ("卡密", "激活码")) and any(
        term in message for term in ("不存在", "无效", "错误")
    ):
        return "卡密无效或不存在，请核对输入及对应产品"
    return "授权未通过，请检查卡密、有效期或网络后重试"


class LicenseRuntime:
    def __init__(self, client_factory, name, *, clock=datetime.now, monotonic=time.monotonic):
        self.client_factory = client_factory
        self.name = name
        self.clock = clock
        self.monotonic = monotonic
        self.client = None
        self.authorized = False
        self.initialized = False
        self.message = "请先激活软件"
        self.last_poll = 0.0
        self.lock = RLock()

    def _client(self):
        if self.client is None:
            self.client = self.client_factory()
        return self.client

    def _local_valid(self):
        cache = self.client.get_cache_info()
        try:
            try:
                expires = datetime.strptime(cache["expire_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                expires = datetime.strptime(cache["expire_time"], "%Y-%m-%d %H:%M")
            verified = datetime.strptime(cache["last_verify"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, TypeError, ValueError):
            return False
        now = self.clock()
        return now < expires and now >= verified - timedelta(seconds=60)

    def _run(self, code=None):
        self.initialized = True
        self.authorized = False
        try:
            client = self._client()
            if code is not None:
                ok, message, _ = client.activate(code)
            elif client.is_activated():
                ok, message, _ = client.verify()
            else:
                self.message = "请先输入卡密激活软件"
                return
            self.authorized = ok is True and self._local_valid()
            self.message = "授权有效" if self.authorized else safe_failure_message(message)
        except Exception as exc:
            # 第三方可能在异常中携带卡密或响应，日志只记录类型。
            logger.warning("授权操作失败 type=%s", type(exc).__name__)
            self.message = "授权服务暂不可用，请检查配置或网络后重试"
        finally:
            self.last_poll = self.monotonic()

    def poll(self):
        with self.lock:
            if not self.initialized:
                return
            if self.authorized and not self._local_valid():
                self.authorized = False
                self.message = "授权已到期或系统时间异常，请重新验证"
            if not self.authorized or self.monotonic() - self.last_poll < 3600:
                return
            self.last_poll = self.monotonic()
            try:
                verified = datetime.strptime(
                    self.client.get_cache_info()["last_verify"], "%Y-%m-%d %H:%M:%S"
                )
            except (KeyError, TypeError, ValueError):
                self._run()
                return
            if self.clock() - verified >= timedelta(hours=24):
                self._run()

    def status(self):
        with self.lock:
            if not self.initialized:
                self._run()
            self.poll()
            cache = self.client.get_cache_info() if self.client else {}
            # 仅返回显示字段，不返回卡密、机器码、凭证版本或签名。
            return {
                "authorized": self.authorized,
                "name": self.name,
                "message": self.message,
                "expire_time": cache.get("expire_time", "") if self.authorized else "",
            }

    def activate(self, code):
        with self.lock:
            self._run(code)
            return self.status()

    def verify(self):
        with self.lock:
            self._run()
            return self.status()


def make_license_runtime():
    # 延迟到首次授权请求读取配置和机器码，模块导入不联网、不启动业务。
    def client_factory():
        from commenlib.license_guard import LicenseClient, LicenseGuardConfig

        with (PROJECT_ROOT / "project.yaml").open(encoding="utf-8") as source:
            cfg = yaml.safe_load(source)
        runtime.name = cfg["app"]["name"]
        license_cfg = cfg["license"]
        return LicenseClient(
            LicenseGuardConfig(
                server_url=license_cfg["server_url"],
                product_id=license_cfg["product_id"],
                offline_grace_days=license_cfg.get("offline_grace_days", 7),
            )
        )

    runtime = LicenseRuntime(client_factory, "AIFACE")
    return runtime


class LocalLicenseGate:
    """Worker 只读本机 API 的授权状态，避免多个进程同时改写凭证。"""

    def __init__(self, port=8000):
        self.url = f"http://127.0.0.1:{port}/api/license/status"
        self.http = httpx.Client(trust_env=False, timeout=60)

    def authorized(self):
        try:
            response = self.http.get(self.url)
            return response.status_code == 200 and response.json().get("authorized") is True
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    def close(self):
        self.http.close()
