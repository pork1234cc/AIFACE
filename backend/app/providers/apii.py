"""供应商单图异步适配；提交不自动重试，错误不携带原始响应。"""

import base64
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.services.assets import MAX_BYTES

BASE_URL = "https://ai.apii.cn"
# 真实联调确认的供应商 CDN；仅此精确域名允许代理的 198.18/15 伪 IP。
PROVIDER_CDN_HOSTS = {"img.ksidc.icu"}
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")
REMOTE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class ProviderError(Exception):
    def __init__(
        self, code: str, message: str, *, uncertain: bool = False, remote_status: str | None = None
    ):
        super().__init__(message)
        self.code, self.message, self.uncertain = code, message, uncertain
        self.remote_status = remote_status


def parse_result(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ProviderError("provider_protocol", "供应商响应格式不符合约定")
    remote_id = body.get("task_id")
    if not isinstance(remote_id, str) or not REMOTE_ID.fullmatch(remote_id):
        raise ProviderError("provider_protocol", "供应商未返回有效任务编号")
    status = body.get("status")
    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ProviderError(
            "unknown_remote_status",
            "供应商返回未识别状态，保留任务待查询",
            remote_status=str(status)[:100],
        )
    result = {
        "task_id": remote_id,
        "status": status,
        "model": body.get("model"),
        "type": body.get("type"),
    }
    if status == "succeeded":
        data = body.get("result", {}).get("data") if isinstance(body.get("result"), dict) else None
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ProviderError("unexpected_image_count", "供应商成功结果必须恰好包含一张图片")
        url = data[0].get("url")
        if not isinstance(url, str) or len(url) > 8192 or not url.startswith("https://"):
            raise ProviderError("provider_protocol", "供应商未返回有效 HTTPS 图片地址")
        result["url"] = url
    return result


class ApiiProvider:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=httpx.Timeout(60, connect=15), transport=transport, follow_redirects=False
        )

    def close(self):
        self.client.close()

    def _headers(self) -> dict:
        try:
            return {"Authorization": f"Bearer {self.settings.require_image_api()}"}
        except RuntimeError as exc:
            raise ProviderError("missing_api_key", "尚未配置模型密钥，请检查后端配置") from exc

    def submit(self, snapshot: dict, images: list[bytes], key: str) -> dict:
        headers = self._headers() | {"Idempotency-Key": key}
        payload = {k: v for k, v in snapshot.items() if k != "inputs"}
        payload["images"] = [base64.b64encode(data).decode("ascii") for data in images]
        try:
            response = self.client.post(
                BASE_URL + "/v1/images/edits", json=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                "submission_unknown", "提交连接中断，受理结果不明，请人工核对", uncertain=True
            ) from exc
        if response.status_code in {400, 401, 403, 404, 413, 422}:
            raise ProviderError("submit_rejected", f"供应商拒绝请求（HTTP {response.status_code}）")
        if response.status_code != 200 and response.status_code != 202:
            raise ProviderError(
                "submission_unknown", "供应商未明确确认受理结果，请人工核对", uncertain=True
            )
        try:
            body = response.json()
            # 一旦拿到有效编号即保存；状态协议问题留给只读查询处理。
            remote_id = body.get("task_id") if isinstance(body, dict) else None
            if not isinstance(remote_id, str) or not REMOTE_ID.fullmatch(remote_id):
                raise ValueError("missing task id")
            return {"task_id": remote_id, "status": "queued"}
        except ValueError as exc:
            raise ProviderError(
                "submission_unknown", "提交响应缺少有效任务编号，请人工核对", uncertain=True
            ) from exc

    def query(self, remote_id: str) -> dict:
        if not REMOTE_ID.fullmatch(remote_id):
            raise ProviderError("invalid_remote_id", "远端任务编号格式不正确")
        try:
            response = self.client.get(BASE_URL + f"/v1/tasks/{remote_id}", headers=self._headers())
            response.raise_for_status()
            result = parse_result(response.json())
            if result["task_id"] != remote_id:
                raise ProviderError("remote_id_mismatch", "供应商返回的任务编号不匹配")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("query_failed", "查询暂时失败，将继续查询原远端任务") from exc

    def download(self, url: str) -> bytes:
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("invalid url")
            if parsed.port not in {None, 443}:
                raise ValueError("invalid port")
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)

            def allowed_address(value: str) -> bool:
                address = ipaddress.ip_address(value)
                return address.is_global or (
                    parsed.hostname in PROVIDER_CDN_HOSTS and address in FAKE_IP_RANGE
                )

            if not addresses or any(not allowed_address(a[4][0]) for a in addresses):
                raise ValueError("non-public host")
            # 下载不附带模型鉴权头，也不自动跟随重定向。
            with self.client.stream("GET", url) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("image too large")
                    chunks.append(chunk)
                return b"".join(chunks)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise ProviderError(
                "download_failed", "图片下载失败，可恢复下载而无需重新生成"
            ) from exc
