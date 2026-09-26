"""授权接线使用模拟客户端，不读取真实凭证或访问授权服务器。"""

from datetime import datetime

import httpx
import pytest

from app.services.licensing import LicenseRuntime, LocalLicenseGate


class FakeLicenseClient:
    def __init__(self, activated=False):
        self.activated = activated
        self.allow = True
        self.calls = []
        self.cache = {
            "expire_time": "9999-12-31 23:59:59",
            "last_verify": "2026-09-26 10:00:00",
            "code": "sensitive-test-code",
        }

    def is_activated(self):
        return self.activated

    def get_cache_info(self):
        return dict(self.cache)

    def activate(self, code):
        self.calls.append(("activate", code))
        self.activated = self.allow
        return self.allow, "模拟激活", {}

    def verify(self):
        self.calls.append(("verify",))
        return self.allow, "模拟验证", {}


def runtime_for(client):
    return LicenseRuntime(
        lambda: client,
        "测试软件",
        clock=lambda: datetime(2026, 9, 26, 10),
        monotonic=lambda: 100.0,
    )


def test_unactivated_cannot_enter_and_activation_reuses_client():
    client = FakeLicenseClient()
    runtime = runtime_for(client)
    assert runtime.status()["authorized"] is False
    assert not client.calls
    assert runtime.activate("test-code")["authorized"] is True
    assert runtime.client is client
    assert client.calls == [("activate", "test-code")]
    assert "sensitive-test-code" not in str(runtime.status())


def test_rejected_and_exception_do_not_enter():
    client = FakeLicenseClient(True)
    client.allow = False
    assert runtime_for(client).status()["authorized"] is False

    def broken():
        raise RuntimeError("sensitive-config")

    status = LicenseRuntime(broken, "测试软件").status()
    assert status["authorized"] is False
    assert "sensitive-config" not in str(status)


def test_existing_credential_verifies_once_on_start():
    client = FakeLicenseClient(True)
    runtime = runtime_for(client)
    assert runtime.status()["authorized"] is True
    assert runtime.status()["authorized"] is True
    assert client.calls == [("verify",)]


def test_permanent_card_is_periodically_verified_and_revocation_blocks():
    client = FakeLicenseClient()
    runtime = runtime_for(client)
    runtime.activate("test-code")
    runtime.clock = lambda: datetime(2026, 9, 27, 11)
    runtime.monotonic = lambda: 3701.0
    client.allow = False
    runtime.poll()
    assert client.calls == [("activate", "test-code"), ("verify",)]
    assert runtime.status()["authorized"] is False


def test_poll_before_24_hours_does_not_call_server():
    client = FakeLicenseClient(True)
    runtime = runtime_for(client)
    runtime.status()
    runtime.clock = lambda: datetime(2026, 9, 26, 12)
    runtime.monotonic = lambda: 3701.0
    runtime.poll()
    assert runtime.status()["authorized"] is True
    assert client.calls == [("verify",)]


def test_expiry_and_clock_rollback_block_without_waiting_for_poll():
    for moment in [datetime(2026, 9, 26, 10, 2), datetime(2026, 9, 26, 9)]:
        client = FakeLicenseClient(True)
        client.cache["expire_time"] = "2026-09-26 10:01:00"
        runtime = runtime_for(client)
        assert runtime.status()["authorized"] is True
        runtime.clock = lambda moment=moment: moment
        assert runtime.status()["authorized"] is False


def test_worker_gate_rejects_bad_payloads_and_network_failure():
    gate = LocalLicenseGate(18000)
    gate.http.close()
    responses = [
        httpx.Response(200, json={"authorized": True}),
        httpx.Response(200, json={"authorized": "true"}),
        httpx.Response(200, json=[]),
        httpx.Response(503, json={"authorized": True}),
    ]
    gate.http = httpx.Client(transport=httpx.MockTransport(lambda _: responses.pop(0)))
    assert gate.authorized() is True
    for _ in range(3):
        assert gate.authorized() is False
    gate.close()

    def unavailable(request):
        raise httpx.ConnectError("模拟失联", request=request)

    gate.http = httpx.Client(transport=httpx.MockTransport(unavailable))
    assert gate.authorized() is False
    gate.close()


def test_invalid_cache_denied():
    client = FakeLicenseClient(True)
    client.cache["last_verify"] = "无效日期"
    assert runtime_for(client).status()["authorized"] is False


def test_minute_precision_expiry_is_accepted_like_component():
    client = FakeLicenseClient(True)
    client.cache["expire_time"] = "2026-09-27 10:00"
    assert runtime_for(client).status()["authorized"] is True


def test_factory_uses_host_configuration_without_real_network(monkeypatch):
    import commenlib.license_guard

    from app.services.licensing import make_license_runtime

    configs = []

    def fake_factory(config):
        configs.append(config)
        return FakeLicenseClient()

    monkeypatch.setattr(commenlib.license_guard, "LicenseClient", fake_factory)
    runtime = make_license_runtime()
    assert runtime.status()["authorized"] is False
    assert configs[0].product_id == "aiface"
    assert configs[0].server_url == "https://xhstools-qedmuqoouc.cn-hangzhou.fcapp.run"
    assert runtime.status()["name"] == "小红书头像工作台"


@pytest.mark.parametrize("action", ["activate", "verify"])
@pytest.mark.parametrize(
    ("upstream_message", "expected"),
    [
        ("激活异常: Expecting value: line 1 column 1 (char 0)", "授权服务返回格式错误"),
        ("服务器响应超时", "授权服务器响应超时"),
        ("无法连接服务器，请检查网络", "无法连接授权服务器"),
        ("卡密不存在 sensitive-test-code", "卡密无效或不存在"),
        ("授权已过期", "授权已过期"),
    ],
)
def test_failure_message_distinguishes_service_and_card_without_leaking(
    action, upstream_message, expected
):
    client = FakeLicenseClient(True)
    setattr(client, action, lambda *args: (False, upstream_message, {}))
    runtime = runtime_for(client)
    status = runtime.activate("sensitive-test-code") if action == "activate" else runtime.verify()
    assert status["authorized"] is False
    assert expected in status["message"]
    assert "sensitive-test-code" not in str(status)
