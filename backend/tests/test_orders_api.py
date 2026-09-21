"""阶段 2 实际迁移、文件与 HTTP 接口的联合验收。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_assets import image_bytes

from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.models.orders import (
    Asset,
    GenerationAction,
    GenerationBatch,
    GenerationTask,
    OrderDelivery,
)
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


def upload(client, order_id, role="material", name="照片.png"):
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
    assert client.get("/api/orders", params={"status": "generating"}).json()["total"] == 0
    assert client.get("/api/orders", params={"page_size": 101}).status_code == 422
    assert client.patch(f"/api/orders/{order_id}", json={"status": "ready"}).status_code == 422
    assert client.get("/api/orders/missing").status_code == 404


def test_material_params_ready_and_restore(client):
    order_id = create(client)
    base = f"/api/orders/{order_id}"
    main = upload(client, order_id, "main", "../../中文照片.png").json()
    material = upload(client, order_id).json()
    assert main["original_name"] == "中文照片.png"
    assert client.get(main["content_url"]).content == image_bytes()
    assert upload(client, order_id, "main").status_code == 409
    params = {
        "base_asset_id": main["id"],
        "changes": [
            {
                "target_description": "左侧人物脸部",
                "change_type": "身份",
                "instruction": "替换身份",
                "source_asset_ids": [material["id"]],
            }
        ],
    }
    response = client.patch(base + "/params", json=params)
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert response.json()["readiness"]["ready"] is True
    assert client.post(base + "/ready").status_code == 200
    assert client.post(base + "/prompt-preview", json={"config": params}).status_code == 200
    response = client.patch(base + f"/images/{material['id']}/active", json={"active": False})
    assert response.json()["status"] == "draft"
    assert response.json()["params"]["changes"][0]["source_asset_ids"] == [material["id"]]
    assert client.get(material["content_url"]).status_code == 200
    assert client.post(base + "/prompt-preview", json={"config": params}).status_code == 422
    assert (
        client.patch(base + f"/images/{material['id']}/active", json={"active": True}).status_code
        == 200
    )
    response = client.patch(base + f"/images/{material['id']}/role", json={"role": "main"})
    assert [a["id"] for a in response.json()["assets"] if a["input_role"] == "main"] == [
        material["id"]
    ]


def test_cross_order_and_invalid_params(client):
    first, second = create(client), create(client)
    foreign = upload(client, second, "main").json()["id"]
    base = f"/api/orders/{first}"
    assert client.patch(base + "/params", json={"hair_source_asset_id": foreign}).status_code == 422
    assert (
        client.patch(base + f"/images/{foreign}/role", json={"role": "material"}).status_code == 404
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


def test_concurrent_upload_and_restore_without_material_count_limit(client):
    order_id = create(client)
    first = upload(client, order_id).json()["id"]
    upload(client, order_id)
    upload(client, order_id)
    barrier = Barrier(2)

    def concurrent_upload(_):
        barrier.wait()
        return upload(client, order_id).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(concurrent_upload, range(2))) == [201, 201]
    assert upload(client, order_id).status_code == 201
    path = f"/api/orders/{order_id}/images/{first}/active"
    assert client.patch(path, json={"active": False}).status_code == 200
    assert upload(client, order_id).status_code == 201
    assert client.patch(path, json={"active": True}).status_code == 200
    data = client.get(f"/api/orders/{order_id}").json()
    assert sum(a["is_active_input"] for a in data["assets"]) == 7
    assert len(data["assets"]) == 7


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
        (base + "/params", {"extra_requirement": "修改"}),
        (base + f"/images/{image_id}/active", {"active": False}),
        (base + f"/images/{image_id}/role", {"role": "main"}),
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
    asset = upload(client, order_id, "main").json()
    response = client.patch(f"/api/orders/{order_id}/params", json={"base_asset_id": asset["id"]})
    assert response.json()["status"] == "draft"
    with TestClient(create_app(client.app.state.settings)) as restarted:
        order = restarted.get(f"/api/orders/{order_id}").json()
        assert order["customer_name"] == "重启保留客户"
        assert order["status"] == "draft"
        assert order["params"]["base_asset_id"] == asset["id"]
        assert restarted.get(asset["content_url"]).content == image_bytes()


def test_delete_order_clears_related_records_and_files(client):
    order_id = create(client, "待删除客户")
    asset = upload(client, order_id, "main").json()
    storage = client.app.state.settings.storage_path
    with write_session(client.app.state.engine) as session:
        batch = GenerationBatch(
            order_id=order_id,
            status="succeeded",
            request_key="delete-test",
            request_hash="hash",
            input_snapshot_json=[],
            params_snapshot_json={},
            style_snapshot_json={},
            prompt_snapshot="测试",
            base_asset_id=asset["id"],
        )
        session.add(batch)
        session.flush()
        task = GenerationTask(
            batch_id=batch.id, slot_index=0, status="succeeded", request_snapshot_json={}
        )
        session.add(task)
        session.flush()
        session.add(GenerationAction(
            scope="delete-test", request_key="delete-test",
            request_hash="hash", batch_id=batch.id,
        ))
        session.add(OrderDelivery(order_id=order_id, asset_id=asset["id"]))
        session.add(Asset(
            order_id=order_id, kind="generated", input_role=None, is_active_input=False,
            generation_task_id=task.id, relative_path=f"orders/{order_id}/outputs/result.png",
            original_name="结果.png", mime_type="image/png", byte_size=1, width=1, height=1,
            sha256="0" * 64,
        ))
    output = storage / "orders" / order_id / "outputs" / "result.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"x")
    other_id = create(client, "保留客户")

    response = client.delete(f"/api/orders/{order_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "files_removed": True}
    assert client.get(f"/api/orders/{order_id}").status_code == 404
    assert client.get("/api/orders").json()["total"] == 1
    assert client.get(f"/api/orders/{other_id}").status_code == 200
    assert not (storage / "orders" / order_id).exists()
    with Session(client.app.state.engine) as session:
        for table in (
            "v2_assets", "v2_generation_batches", "v2_generation_tasks",
            "v2_generation_actions", "v2_order_deliveries",
        ):
            assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert not session.execute(text("PRAGMA foreign_key_check")).all()
    assert client.delete(f"/api/orders/{order_id}").status_code == 404


def test_delete_order_rejects_open_generation(client):
    order_id = create(client)
    with write_session(client.app.state.engine) as session:
        session.add(GenerationBatch(
            order_id=order_id, status="running", request_key="open-delete",
            request_hash="hash", input_snapshot_json=[], params_snapshot_json={},
            style_snapshot_json={}, prompt_snapshot="测试",
        ))
    response = client.delete(f"/api/orders/{order_id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "order_has_open_tasks"
    assert client.get(f"/api/orders/{order_id}").status_code == 200
