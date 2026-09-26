"""区域要求、素材编号与快照的一致性验证。"""

import base64
import io

import numpy as np
import pytest
from PIL import Image
from test_orders_api import client as api_client
from test_orders_api import create, upload
from test_unified_creation import example

from app.schemas.orders import Params
from app.services import regions
from app.services.orders import BusinessError
from app.services.prompts import build_initial_prompt

client = api_client


def region(**overrides):
    return {
        "id": "hair",
        "label": "头发",
        "target_description": "画面左侧人物的头发",
        "instruction": "只参考发色",
        "preserve_instruction": "保留长度",
        "source_asset_ids": ["b"],
        **overrides,
    }


def config(**overrides):
    return Params.model_validate(
        {
            "base_asset_id": "main",
            "material_slots": [None, "a", "b"],
            "region_asset_id": "main",
            "region_prompts": [region()],
            **overrides,
        }
    )


def test_regions_map_sparse_materials_and_keep_snapshot():
    order, assets, payload = example()
    payload.config = config(extra_requirement="保持构图")
    result = build_initial_prompt(order, assets, payload)
    assert "素材3 对应图片 3" in result["prompt"]
    assert "目标为图片 1 中的画面左侧人物的头发；素材来源：图片 3" in result["prompt"]
    assert result["prompt"].count("只参考发色") == 1
    assert "保留长度" in result["prompt"] and "保持构图" in result["prompt"]
    assert result["params"]["region_prompts"][0]["source_asset_ids"] == ["b"]


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"region_asset_id": "old"}, "stale_regions"),
        ({"region_prompts": [region(), region()]}, "duplicate_region"),
        ({"region_prompts": [region(source_asset_ids=["foreign"])]}, "invalid_source"),
        ({"material_slots": [None, "a", None]}, "invalid_source"),
        ({"region_prompts": [region(instruction="")]}, "missing_region_instruction"),
        ({"region_prompts": [region(instruction="使用素材1")]}, "missing_material"),
    ],
)
def test_invalid_region_bindings_rejected(overrides, code):
    order, assets, payload = example()
    payload.config = config(**overrides)
    with pytest.raises(BusinessError) as error:
        build_initial_prompt(order, assets, payload)
    assert error.value.code == "order_not_ready"
    # readiness 将业务错误合并，但直接校验仍保留精确错误码。
    from app.services.prompts import validate_sources

    with pytest.raises(BusinessError) as error:
        validate_sources(payload.config, assets)
    assert error.value.code == code


def test_empty_region_is_not_an_edit_and_preserve_only_is_supported():
    order, assets, payload = example()
    payload.config = config(
        region_prompts=[region(source_asset_ids=[], instruction="", preserve_instruction="")]
    )
    assert "区域【" not in build_initial_prompt(order, assets, payload)["prompt"]
    payload.config.region_prompts[0].preserve_instruction = "保留原发型"
    assert (
        "不修改此区域内容；保留要求：保留原发型"
        in build_initial_prompt(order, assets, payload)["prompt"]
    )


def test_mask_indices_match_detected_regions():
    labels = np.zeros((32, 32), dtype=np.uint8)
    labels[5:20, 5:20] = 1
    labels[:5, :] = 17
    result = regions.summarize_mask(labels)
    hair = next(item for item in result["regions"] if item["id"] == "hair")
    assert not any(item["id"] == "eyes" for item in result["regions"])
    png = base64.b64decode(result["mask_url"].split(",", 1)[1])
    with Image.open(io.BytesIO(png)) as mask:
        assert mask.getpixel((0, 0))[0] == hair["mask_value"]
    with pytest.raises(BusinessError, match="清晰人像"):
        regions.summarize_mask(np.zeros((32, 32), dtype=np.uint8))


def test_missing_model_returns_actionable_error(tmp_path):
    with pytest.raises(BusinessError) as error:
        regions.recognize_regions(b"", tmp_path / "missing.onnx")
    assert error.value.code == "region_model_unavailable"


def test_region_api_checks_ownership_and_does_not_generate(client, monkeypatch):
    order_id = create(client)
    main = upload(client, order_id, "main").json()["id"]
    other = create(client)
    foreign = upload(client, other, "main").json()["id"]
    calls = []

    def recognize(data):
        calls.append(data)
        return {"regions": [], "mask_url": "", "width": 512, "height": 512}

    monkeypatch.setattr(regions, "recognize_regions", recognize)
    url = f"/api/orders/{order_id}"
    assert client.patch(f"{url}/params", json={"base_asset_id": main}).status_code == 200
    assert client.post(f"{url}/images/{foreign}/regions").status_code == 404
    assert not calls
    response = client.post(f"{url}/images/{main}/regions")
    assert response.status_code == 200
    assert response.json()["asset_id"] == main and len(calls) == 1
    assert client.get(f"{url}/batches").json()["items"] == []
    params = config(
        base_asset_id=main,
        region_asset_id=main,
        material_slots=[None, None, None],
        region_prompts=[region(source_asset_ids=[])],
    ).model_dump()
    saved = client.patch(f"{url}/params", json=params)
    assert saved.status_code == 200, saved.text
    assert client.get(url).json()["params"]["region_prompts"] == params["region_prompts"]
