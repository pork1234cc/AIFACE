"""供应商协议与错误分类，不访问真实网络。"""

import base64
import hashlib
import io
import json

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.providers.apii import ApiiProvider, ProviderError, parse_result


def test_four_images_and_single_submit():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"task_id": "remote-1", "status": "queued"})

    provider = ApiiProvider(
        Settings(_env_file=None, image_api="secret"), httpx.MockTransport(handler)
    )
    try:
        assert provider.submit({"async": True}, [b"a", b"b", b"c", b"d"], "stable")["task_id"]
        body = json.loads(requests[0].content)
        assert body["images"] == ["YQ==", "Yg==", "Yw==", "ZA=="]
        assert requests[0].headers["Idempotency-Key"] == "stable"
        assert "n" not in body
    finally:
        provider.close()


def test_large_generated_png_is_compacted_for_provider_without_changing_source():
    pixels = hashlib.shake_256(b"large-generated-image").digest(1600 * 1600 * 3)
    picture = Image.frombytes("RGB", (1600, 1600), pixels)
    source = io.BytesIO()
    picture.save(source, format="PNG")
    original = source.getvalue()
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(202, json={"task_id": "large-image", "status": "queued"})

    provider = ApiiProvider(
        Settings(_env_file=None, image_api="secret"), httpx.MockTransport(handler)
    )
    try:
        provider.submit({"async": True}, [original, b"small"], "large-image-key")
        assert len(seen) == 1
        assert len(seen[0].content) < 5 * 1024 * 1024
        sent = json.loads(seen[0].content)["images"]
        compacted = base64.b64decode(sent[0])
        with Image.open(io.BytesIO(compacted)) as delivered:
            assert delivered.format == "JPEG"
            assert delivered.size == (1600, 1600)
        assert base64.b64decode(sent[1]) == b"small"
        assert original == source.getvalue()
    finally:
        provider.close()


@pytest.mark.parametrize("code,unknown", [(401, False), (422, False), (500, True), (409, True)])
def test_submit_http_classification(code, unknown):
    provider = ApiiProvider(
        Settings(_env_file=None, image_api="secret"),
        httpx.MockTransport(
            lambda request: httpx.Response(code, text="secret and provider details")
        ),
    )
    try:
        with pytest.raises(ProviderError) as error:
            provider.submit({}, [], "key")
        assert error.value.uncertain is unknown
        assert "secret" not in str(error.value)
    finally:
        provider.close()


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"task_id": "x", "status": "unknown"},
        {"task_id": "x", "status": "succeeded", "result": {"data": []}},
        {"task_id": "x", "status": "succeeded", "result": {"data": [{}, {}]}},
    ],
)
def test_protocol_rejects_ambiguous_results(body):
    with pytest.raises(ProviderError):
        parse_result(body)


def test_unknown_status_kept_separately_from_public_error():
    with pytest.raises(ProviderError) as error:
        parse_result({"task_id": "remote", "status": "provider-new-state"})
    assert error.value.remote_status == "provider-new-state"
    assert "provider-new-state" not in error.value.message


def test_verified_cdn_supports_local_fake_ip_proxy(monkeypatch):
    monkeypatch.setattr(
        "app.providers.apii.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("198.18.1.131", 443))],
    )

    def handler(request):
        assert "Authorization" not in request.headers
        assert request.url.host == "img.ksidc.icu"
        return httpx.Response(200, content=b"image-data")

    provider = ApiiProvider(Settings(_env_file=None), httpx.MockTransport(handler))
    try:
        assert provider.download("https://img.ksidc.icu/example.png") == b"image-data"
        with pytest.raises(ProviderError):
            provider.download("https://untrusted.example/example.png")
        with pytest.raises(ProviderError):
            provider.download("https://img.ksidc.icu.evil.example/example.png")
    finally:
        provider.close()
