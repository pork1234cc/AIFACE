"""阶段 2 实际迁移、文件与 HTTP 接口的联合验收。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from test_assets import image_bytes

from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.services.orders import get_order, write_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACE_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("AIFACE_STORAGE_PATH", str(tmp_path / "storage"))
    command.upgrade(Config(str(PROJECT_ROOT / "backend/alembic.ini")), "head")
    with TestClient(create_app(Settings(_env_file=None))) as value:
        yield value


def create(client, name="测试客户"):
    response = client.post("/api/orders", json={"customer_name": name, "note": "中文备注"})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, order_id, role="person_aux", name="照片.png"):
    return client.post(
        f"/api/orders/{order_id}/images",
        data={"role": role},
        files={"file": (name, image_bytes(), "image/png")},
    )


def test_order_roundtrip_and_filters(client):
    order_id = create(client)
    assert client.get(f"/api/orders/{order_id}").json()["readiness"]["ready"] is False
    assert client.post(f"/api/orders/{order_id}/ready").status_code == 422
    response = client.patch(f"/api/orders/{order_id}", json={"customer_name": "改名"})
    assert response.json()["note"] == "中文备注"
    assert client.get("/api/orders", params={"q": "改名"}).json()["total"] == 1
    assert client.get("/api/orders", params={"status": "ready"}).json()["total"] == 0
    assert client.get("/api/orders", params={"page_size": 101}).status_code == 422
    assert client.patch(f"/api/orders/{order_id}", json={"status": "ready"}).status_code == 422
    assert client.get("/api/orders/missing").status_code == 404


def test_material_params_ready_and_restore(client):
    order_id = create(client)
    base = f"/api/orders/{order_id}"
    main = upload(client, order_id, "person_main", "../../中文照片.png").json()
    aux = upload(client, order_id).json()
    ref = upload(client, order_id, "reference").json()
    assert main["original_name"] == "中文照片.png"
    assert "relative_path" not in main
    assert client.get(main["content_url"]).content == image_bytes()
    assert upload(client, order_id, "reference").status_code == 409
    assert upload(client, order_id, "person_main").status_code == 409
    response = client.patch(
        base + "/params",
        json={
            "hair_source_asset_id": aux["id"],
            "clothes_mode": "reference",
            "clothes_source_asset_id": ref["id"],
            "glasses_keep": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert client.post(base + "/ready").status_code == 200
    inputs = [{"asset_id": a["id"], "role": a["input_role"]} for a in [main, aux, ref]]
    preview = client.post(base + "/prompt-preview", json={"inputs": inputs})
    assert preview.status_code == 200
    assert "去掉眼镜" in preview.json()["prompt"]
    assert client.post(base + "/prompt-preview", json={"inputs": inputs[:2]}).status_code == 422
    response = client.patch(base + f"/images/{ref['id']}/active", json={"active": False})
    assert response.json()["status"] == "draft"
    assert response.json()["params"]["clothes_source_asset_id"] is None
    assert client.get(ref["content_url"]).status_code == 200
    assert (
        client.patch(base + f"/images/{ref['id']}/active", json={"active": True}).status_code == 200
    )
    # 恢复图片不会擅自恢复已清空的参数。
    assert client.get(base).json()["params"]["clothes_source_asset_id"] is None
    response = client.patch(base + f"/images/{aux['id']}/role", json={"role": "person_main"})
    active = [a for a in response.json()["assets"] if a["is_active_input"]]
    assert [a["id"] for a in active if a["input_role"] == "person_main"] == [aux["id"]]


def test_cross_order_and_invalid_params(client):
    first, second = create(client), create(client)
    foreign = upload(client, second, "person_main").json()["id"]
    base = f"/api/orders/{first}"
    assert client.patch(base + "/params", json={"hair_source_asset_id": foreign}).status_code == 422
    assert (
        client.patch(base + f"/images/{foreign}/role", json={"role": "person_aux"}).status_code
        == 404
    )
    for params in [
        {"clothes_mode": "reference"},
        {"glasses_keep": None},
        {"background": "black"},
        {"output_count": 4},
        {"hair_source_asset_id": ""},
        {"glasses_keep": "false"},
    ]:
        assert client.patch(base + "/params", json=params).status_code == 422


def test_concurrent_upload_and_restore_limits(client):
    order_id = create(client)
    first = upload(client, order_id).json()["id"]
    upload(client, order_id)
    upload(client, order_id)
    barrier = Barrier(2)

    def concurrent_upload(_):
        barrier.wait()
        return upload(client, order_id).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(concurrent_upload, range(2))) == [201, 409]
    assert upload(client, order_id).status_code == 409
    path = f"/api/orders/{order_id}/images/{first}/active"
    assert client.patch(path, json={"active": False}).status_code == 200
    assert upload(client, order_id).status_code == 201
    assert client.patch(path, json={"active": True}).status_code == 409
    data = client.get(f"/api/orders/{order_id}").json()
    assert sum(a["is_active_input"] for a in data["assets"]) == 4
    assert len(data["assets"]) == 5


@pytest.mark.parametrize("status", ["closed", "completed"])
def test_terminal_order_is_readonly(client, status):
    order_id = create(client)
    image_id = upload(client, order_id).json()["id"]
    with write_session(client.app.state.engine) as session:
        get_order(session, order_id).status = status
    base = f"/api/orders/{order_id}"
    assert upload(client, order_id).status_code == 409
    for path, data in [
        (base, {"note": "不能改"}),
        (base + "/params", {"glasses_keep": False}),
        (base + f"/images/{image_id}/active", {"active": False}),
        (base + f"/images/{image_id}/role", {"role": "person_main"}),
    ]:
        assert client.patch(path, json=data).status_code == 409
    assert client.post(base + "/ready").status_code == 409
    assert client.get(base).status_code == 200


def test_styles_and_generation_requires_valid_request(client):
    style = client.get("/api/styles").json()["items"][0]
    assert style["initial_count"] == 1 and style["revision_count"] == 1
    assert style["reference_images"] == []
    assert client.get("/api/styles/q_crayon_001").status_code == 200
    assert client.get("/api/styles/unknown").status_code == 404
    assert client.post(f"/api/orders/{create(client)}/generate", json={}).status_code == 422


def test_business_survives_app_restart(client):
    order_id = create(client, "重启保留客户")
    asset = upload(client, order_id, "person_main").json()
    response = client.patch(
        f"/api/orders/{order_id}/params", json={"hair_source_asset_id": asset["id"]}
    )
    assert response.json()["status"] == "ready"
    with TestClient(create_app(client.app.state.settings)) as restarted:
        order = restarted.get(f"/api/orders/{order_id}").json()
        assert order["customer_name"] == "重启保留客户"
        assert order["status"] == "ready"
        assert order["params"]["hair_source_asset_id"] == asset["id"]
        assert restarted.get(asset["content_url"]).content == image_bytes()
