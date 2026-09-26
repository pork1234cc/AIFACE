"""供应商单图异步适配；提交不自动重试，错误不携带原始响应。"""

import base64
import io
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.providers.image_payload import (
    decode_base64_image,
    is_mask_url,
    validate_mask,
    validate_mask_url,
)
from app.services.assets import MAX_BYTES

# 真实联调确认的供应商 CDN；仅此精确域名允许代理的 198.18/15 伪 IP。
PROVIDER_CDN_HOSTS = {"img.ksidc.icu"}
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")
REMOTE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
# 给提示词与 JSON 字段留出空间；这是客户端保守目标，并非供应商公布的上限。
INLINE_IMAGES_TARGET_BYTES = 4_500_000


def prepare_inline_images(images: list[bytes]) -> list[bytes]:
    """只压缩提交副本，不修改资产文件或任务输入快照。"""

    def encoded_size(values: list[bytes]) -> int:
        return sum(4 * ((len(value) + 2) // 3) for value in values)

    prepared = list(images)
    if encoded_size(prepared) <= INLINE_IMAGES_TARGET_BYTES:
        return prepared
    for index in sorted(range(len(prepared)), key=lambda item: len(prepared[item]), reverse=True):
        if encoded_size(prepared) <= INLINE_IMAGES_TARGET_BYTES:
            break
        try:
            with Image.open(io.BytesIO(prepared[index])) as source:
                picture = ImageOps.exif_transpose(source)
                if picture.mode in {"RGBA", "LA"} or "transparency" in picture.info:
                    transparent = picture.convert("RGBA")
                    background = Image.new("RGB", picture.size, "white")
                    background.paste(transparent, mask=transparent.getchannel("A"))
                    picture = background
                else:
                    picture = picture.convert("RGB")
                output = io.BytesIO()
                picture.save(output, format="JPEG", quality=90, optimize=True)
                compacted = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ProviderError(
                "invalid_provider_input", "模型输入图片无法压缩，请重新上传或选择其他图片"
            ) from exc
        if len(compacted) < len(prepared[index]):
            prepared[index] = compacted
    if encoded_size(prepared) > INLINE_IMAGES_TARGET_BYTES:
        raise ProviderError(
            "provider_payload_too_large", "模型输入图片总量过大，请减少素材或换用更小的图片后重试"
        )
    return prepared


class ProviderError(Exception):
    def __init__(
        self, code: str, message: str, *, uncertain: bool = False, remote_status: str | None = None
    ):
        super().__init__(message)
        self.code, self.message, self.uncertain = code, message, uncertain
        self.remote_status = remote_status


def parse_image_result(body: dict) -> dict:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ProviderError("unexpected_image_count", "供应商成功结果必须恰好包含一张图片")
    if isinstance(data[0].get("b64_json"), str):
        try:
            decode_base64_image(data[0]["b64_json"])
        except ValueError as exc:
            raise ProviderError("provider_protocol", "供应商返回无效的 Base64 图片") from exc
        return {"b64_json": data[0]["b64_json"]}
    url = data[0].get("url")
    if not isinstance(url, str) or len(url) > 8192 or not url.startswith("https://"):
        raise ProviderError("provider_protocol", "供应商未返回有效 HTTPS 图片地址")
    return {"url": url}


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
        result.update(parse_image_result(body.get("result")))
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
        payload = {k: v for k, v in snapshot.items() if k != "inputs" and not k.startswith("_")}
        api_url = snapshot.get("_api_url", self.settings.image_api_url)
        mode = snapshot.get("_mode", "edit")
        if mode == "generate" and (images or payload.get("mask")):
            raise ProviderError("invalid_provider_input", "纯文生图不能附带参考图或遮罩")
        if payload.get("mask"):
            try:
                value = payload["mask"]
                if is_mask_url(value):
                    validate_mask_url(value)
                    mask_data = self.download(value)
                else:
                    mask_data = decode_base64_image(value)
                if not images:
                    raise ValueError("遮罩需要底图")
                with Image.open(io.BytesIO(images[0])) as base:
                    validate_mask(mask_data, base.size)
                payload["mask"] = base64.b64encode(mask_data).decode("ascii")
            except (ValueError, OSError, ProviderError) as exc:
                raise ProviderError(
                    "invalid_mask", "遮罩读取失败或尺寸、透明区域不符合要求"
                ) from exc
            # 遮罩编辑保留底图原字节，避免 EXIF 转向或透明度变化造成坐标错位。
            prepared = images
        else:
            prepared = prepare_inline_images(images)
        if mode == "edit":
            payload["images"] = [base64.b64encode(data).decode("ascii") for data in prepared]
        endpoint = "generations" if mode == "generate" else "edits"
        try:
            response = self.client.post(
                api_url + f"/v1/images/{endpoint}",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(600 if payload.get("async") is False else 60, connect=15),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                "submission_unknown", "提交连接中断，受理结果不明，请人工核对", uncertain=True
            ) from exc
        if response.status_code in {400, 401, 403, 404, 413, 422}:
            if response.status_code == 413:
                raise ProviderError(
                    "submit_rejected", "供应商拒绝请求（HTTP 413）：输入图片可能超过大小限制"
                )
            raise ProviderError("submit_rejected", f"供应商拒绝请求（HTTP {response.status_code}）")
        if response.status_code != 200 and response.status_code != 202:
            raise ProviderError(
                "submission_unknown", "供应商未明确确认受理结果，请人工核对", uncertain=True
            )
        try:
            body = response.json()
            if isinstance(body, dict) and "data" in body:
                try:
                    return {"status": "succeeded", **parse_image_result(body)}
                except ProviderError as exc:
                    raise ValueError("invalid synchronous result") from exc
            # 一旦拿到有效编号即保存；状态协议问题留给只读查询处理。
            remote_id = body.get("task_id") if isinstance(body, dict) else None
            if not isinstance(remote_id, str) or not REMOTE_ID.fullmatch(remote_id):
                raise ValueError("missing task id")
            return {"task_id": remote_id, "status": "queued"}
        except ValueError as exc:
            raise ProviderError(
                "submission_unknown", "提交响应缺少有效任务编号，请人工核对", uncertain=True
            ) from exc

    def query(self, remote_id: str, api_url: str | None = None) -> dict:
        if not REMOTE_ID.fullmatch(remote_id):
            raise ProviderError("invalid_remote_id", "远端任务编号格式不正确")
        try:
            response = self.client.get(
                (api_url or self.settings.image_api_url) + f"/v1/tasks/{remote_id}",
                headers=self._headers(),
            )
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
