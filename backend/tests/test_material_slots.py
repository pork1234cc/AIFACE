"""固定素材位置和输入映射回归。"""

import pytest
from test_assets import image_bytes
from test_orders_api import client as api_client
from test_orders_api import create
from test_revisions import generated, request, revise
from test_unified_creation import example

from app.schemas.orders import Params
from app.services.orders import BusinessError
from app.services.prompts import build_initial_prompt

client = api_client


def test_numbered_material_gap_maps_to_actual_image():
    order, assets, payload = example()
    payload.config = Params(
        base_asset_id="main",
        material_slots=[None, "a", "b"],
        extra_requirement="素材2用于发型，素材3用于服装",
    )
    result = build_initial_prompt(order, assets, payload)
    assert result["inputs"][1]["asset_id"] == "a"
    assert "素材2 对应图片 2" in result["prompt"]
    assert "素材3 对应图片 3" in result["prompt"]
    assert result["params"]["material_slots"] == [None, "a", "b"]


def test_missing_numbered_material_rejected():
    order, assets, payload = example()
    payload.config = Params(
        base_asset_id="main", material_slots=[None, "a", None], extra_requirement="使用素材1的发型"
    )
    with pytest.raises(BusinessError, match="素材1"):
        build_initial_prompt(order, assets, payload)


@pytest.mark.parametrize("slots", [["a", "a", None], ["main", None, None], ["foreign", None, None]])
def test_invalid_slots_rejected(slots):
    order, assets, payload = example()
    payload.config = Params(base_asset_id="main", material_slots=slots)
    with pytest.raises(BusinessError):
        build_initial_prompt(order, assets, payload)


def test_slot_replacement_and_removal_keep_other_numbers(client):
    order_id = create(client)
    path = f"/api/orders/{order_id}/image-slots"

    def put(slot):
        response = client.post(
            path + f"/{slot}", files={"file": ("素材.png", image_bytes(), "image/png")}
        )
        assert response.status_code == 200, response.text
        return response.json()

    order = put("main")
    main = order["params"]["base_asset_id"]
    first = put("1")["params"]["material_slots"][0]
    second = put("2")["params"]["material_slots"][1]
    put("3")
    replaced = put("1")
    assert replaced["params"]["material_slots"][0] != first
    assert replaced["params"]["material_slots"][1] == second
    assert replaced["params"]["base_asset_id"] == main
    response = client.post(path + "/1/clear")
    assert response.status_code == 200
    assert response.json()["params"]["material_slots"][:2] == [None, second]
    assert client.get(f"/api/images/{first}/content").status_code == 200
    before = response.json()["params"]
    invalid = client.post(path + "/2", files={"file": ("bad.png", b"bad", "image/png")})
    assert invalid.status_code == 415
    assert client.get(f"/api/orders/{order_id}").json()["params"] == before


def test_fourth_and_fifth_material_slots_are_available_for_generation(client):
    order_id = create(client)
    path = f"/api/orders/{order_id}"
    main = client.post(
        path + "/image-slots/main", files={"file": ("主图.png", image_bytes(), "image/png")}
    ).json()["params"]["base_asset_id"]
    materials = []
    for number in range(1, 6):
        response = client.post(
            path + f"/image-slots/{number}",
            files={"file": (f"素材{number}.png", image_bytes(), "image/png")},
        )
        assert response.status_code == 200, response.text
        materials.append(response.json()["params"]["material_slots"][number - 1])
    config = response.json()["params"] | {
        "extra_requirement": "素材4用于发型，素材5用于服装",
        "output_format": "webp",
    }
    preview = client.post(path + "/prompt-preview", json={"config": config})
    assert preview.status_code == 200, preview.text
    assert [item["asset_id"] for item in preview.json()["inputs"]] == [main, *materials]
    assert "素材5 对应图片 6" in preview.json()["prompt"]
    skipped = client.post(
        path + "/image-slots/7", files={"file": ("跳号.png", image_bytes(), "image/png")}
    )
    assert skipped.status_code == 422


def test_replacing_original_preserves_generated_base_and_blocks_during_task(client):
    order_id, result_id, _ = generated(client)
    path = f"/api/orders/{order_id}"
    assert client.patch(path + "/params", json={"base_asset_id": result_id}).status_code == 200
    replacement = client.post(
        path + "/image-slots/main", files={"file": ("新主图片.png", image_bytes(), "image/png")}
    )
    assert replacement.status_code == 200
    assert replacement.json()["params"]["base_asset_id"] == result_id
    main = next(
        a for a in replacement.json()["assets"] if a["kind"] == "input" and a["is_active_input"]
    )
    assert main["id"] != result_id
    revise(client, order_id, request(result_id))
    assert client.post(path + "/image-slots/main/clear").status_code == 409
    assert client.get(path).json()["params"]["base_asset_id"] == result_id
