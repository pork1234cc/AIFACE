"""内联图片及透明遮罩校验；不联网、不改变原图方向或尺寸。"""

import base64
import binascii
import io
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def decode_base64_image(value: str) -> bytes:
    if value.startswith("data:"):
        header, separator, value = value.partition(",")
        if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise ValueError("图片 Data URL 格式无效")
    if not value or len(value) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError("内联图片为空或超过 20 MiB")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("图片 Base64 格式无效") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("内联图片超过 20 MiB")
    return data


def is_mask_url(value: str) -> bool:
    return value.startswith(("https://", "http://"))


def validate_mask_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or len(value) > 8192
    ):
        raise ValueError("遮罩地址须为无账号信息的公网 HTTPS 图片地址")


def validate_mask(data: bytes, size: tuple[int, int]) -> None:
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.size != size:
                raise ValueError("遮罩尺寸必须与本次底图一致")
            if picture.width * picture.height > 40_000_000:
                raise ValueError("遮罩像素过多")
            if picture.format not in {"PNG", "WEBP"} or getattr(picture, "n_frames", 1) != 1:
                raise ValueError("遮罩须为静态透明 PNG 或 WebP 图片")
            if "A" not in picture.getbands() and "transparency" not in picture.info:
                raise ValueError("遮罩必须包含透明通道")
            alpha = picture.convert("RGBA").getchannel("A")
            if alpha.getextrema()[0] != 0:
                raise ValueError("遮罩必须包含需要重绘的完全透明区域")
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("遮罩图片无效") from exc
