"""业务回归显式注入模拟授权；生产代码没有跳过授权的环境开关。"""

import pytest


class AuthorizedTestRuntime:
    def status(self):
        return {"authorized": True, "name": "测试授权", "message": "模拟通过", "expire_time": ""}

    def poll(self):
        pass


@pytest.fixture(autouse=True)
def isolate_license_server(monkeypatch):
    # 授权专项测试通过 create_app(license_runtime=...) 显式覆盖此模拟。
    monkeypatch.setattr("app.main.make_license_runtime", AuthorizedTestRuntime)
