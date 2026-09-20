"""格式验证和路径边界。"""

import io

import pytest
from PIL import Image

from app.models.orders import Asset
from app.services import assets
from app.services.orders import BusinessError


def image_bytes(format="PNG", size=(16, 12)):
    output = io.BytesIO()
    Image.new("RGB", size, "pink").save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_decode_supported_formats(format, mime):
    decoded = assets.decode_upload(io.BytesIO(image_bytes(format)))
    assert decoded[2:] == (mime, 16, 12)


@pytest.mark.parametrize(
    "data", [b"", b"<svg></svg>", b"fake.png", image_bytes()[:40], image_bytes("GIF")]
)
def test_reject_invalid_images(data):
    with pytest.raises(BusinessError) as error:
        assets.decode_upload(io.BytesIO(data))
    assert error.value.status == 415


def test_upload_limits(monkeypatch):
    monkeypatch.setattr(assets, "MAX_BYTES", 10)
    with pytest.raises(BusinessError, match="20 MiB"):
        assets.decode_upload(io.BytesIO(b"x" * 11))
    monkeypatch.setattr(assets, "MAX_BYTES", 100000)
    monkeypatch.setattr(assets, "MAX_PIXELS", 10)
    with pytest.raises(BusinessError, match="4000 万"):
        assets.decode_upload(io.BytesIO(image_bytes()))


def test_path_cannot_escape_order(tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("保密", encoding="utf-8")
    with pytest.raises(BusinessError):
        assets.content_path(tmp_path, Asset(order_id="test", relative_path="secret.txt"))
    with pytest.raises(BusinessError):
        assets.content_path(
            tmp_path, Asset(order_id="test", relative_path="orders/test/missing.png")
        )
