"""自定义风格持久化、只读边界、校验及不可变生成快照。"""

import pytest
from sqlalchemy.orm import Session
from test_orders_api import client as api_client
from test_orders_api import create, upload

from app.models.orders import GenerationBatch

client = api_client


def new_style(client):
    response = client.post(
        "/api/styles",
        json={
            "style_name": "  清透水彩  ",
            "description": "轻盈透明",
            "prompt": "使用透明水彩晕染与纸张纹理。",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_list_read_and_update(client):
    style = new_style(client)
    assert style["style_name"] == "清透水彩"
    assert style["is_builtin"] is False
    assert style["version"] == "1"
    assert client.get(f"/api/styles/{style['style_id']}").json() == style
    assert len(client.get("/api/styles").json()["items"]) == 2
    payload = {"style_name": "油画", "prompt": "厚涂油画", "expected_version": 1}
    changed = client.put(f"/api/styles/{style['style_id']}", json=payload)
    assert changed.status_code == 200
    assert changed.json()["version"] == "2"
    assert client.put(f"/api/styles/{style['style_id']}", json=payload).status_code == 409
    builtin = client.get("/api/styles/q_crayon_001").json()
    assert client.put("/api/styles/q_crayon_001", json=payload).status_code == 403
    assert client.get("/api/styles/q_crayon_001").json() == builtin


@pytest.mark.parametrize(
    "payload",
    [
        {"style_name": " ", "prompt": "水彩"},
        {"style_name": "水彩", "prompt": " \n "},
        {"style_name": "水彩", "prompt": "字" * 4001},
        {"style_name": "字" * 61, "prompt": "水彩"},
        {"style_name": "水彩", "prompt": "水彩", "description": "字" * 201},
        {"style_name": "水彩", "prompt": "水彩", "style_id": "q_crayon_001"},
    ],
)
def test_invalid_custom_style(client, payload):
    assert client.post("/api/styles", json=payload).status_code == 422
    assert len(client.get("/api/styles").json()["items"]) == 1


def test_custom_style_preview_save_and_immutable_snapshot(client):
    style = new_style(client)
    order_id = create(client)
    main = upload(client, order_id, "main").json()
    config = {"base_asset_id": main["id"], "style_id": style["style_id"]}
    assert client.patch(f"/api/orders/{order_id}/params", json=config).status_code == 200
    payload = {"config": config}
    preview = client.post(f"/api/orders/{order_id}/prompt-preview", json=payload)
    assert preview.status_code == 200
    assert style["prompt_template"]["system_style"] in preview.json()["prompt"]
    assert len(preview.json()["inputs"]) == 1
    headers = {"Idempotency-Key": "custom-style-test"}
    created = client.post(f"/api/orders/{order_id}/generate", json=payload, headers=headers)
    assert created.status_code == 202
    batch_id = created.json()["batch_id"]
    assert (
        client.put(
            f"/api/styles/{style['style_id']}",
            json={
                "style_name": "新版",
                "prompt": "粗犷油画厚涂",
                "expected_version": 1,
            },
        ).status_code
        == 200
    )
    with Session(client.app.state.engine) as session:
        batch = session.get(GenerationBatch, batch_id)
        assert batch.style_snapshot_json == preview.json()["style"]
        assert batch.prompt_snapshot == preview.json()["prompt"]
    assert (
        client.post(f"/api/orders/{order_id}/generate", json=payload, headers=headers).json()[
            "batch_id"
        ]
        == batch_id
    )
    new_preview = client.post(f"/api/orders/{order_id}/prompt-preview", json=payload).json()
    assert "粗犷油画厚涂" in new_preview["prompt"]
    assert new_preview["style"]["version"] == "2"


def test_unknown_style_rejected_for_save_and_preview(client):
    order_id = create(client)
    main = upload(client, order_id, "main").json()
    config = {"base_asset_id": main["id"], "style_id": "custom_" + "0" * 32}
    assert client.patch(f"/api/orders/{order_id}/params", json=config).status_code == 404
    assert (
        client.post(f"/api/orders/{order_id}/prompt-preview", json={"config": config}).status_code
        == 404
    )
