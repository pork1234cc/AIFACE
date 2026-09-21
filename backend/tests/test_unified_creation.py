"""统一底图创作的契约、素材映射和默认保留回归。"""

import pytest
from pydantic import ValidationError

from app.models.orders import Asset, Order
from app.schemas.orders import InitialInputs, Params
from app.services.orders import BusinessError
from app.services.prompts import build_initial_prompt


def example(changes=None):
    config = Params(schema_version=2, base_asset_id="main", changes=changes or [])
    order = Order(id="order", status="draft", params_json=config.model_dump())
    assets = [
        Asset(id=key, order_id="order", kind="input", input_role=role, is_active_input=True)
        for key, role in [("main", "main"), ("a", "material"), ("b", "material")]
    ]
    return order, assets, InitialInputs(config=config)


def test_style_only_preserves_entire_base():
    result = build_initial_prompt(*example())
    assert result["inputs"] == [{"asset_id": "main", "role": "base"}]
    assert "人物和物品数量" in result["prompt"]
    assert "单人" not in result["prompt"]
    assert result["style"]["version"] == "2.0.0"
    assert result["target_count"] == 1


def test_material_dedup_and_mapping():
    changes = [
        dict(
            target_description=target,
            change_type="脸部",
            instruction="替换身份",
            source_asset_ids=["a"],
        )
        for target in ["左侧人物", "右侧人物"]
    ]
    result = build_initial_prompt(*example(changes))
    assert len(result["inputs"]) == 2
    assert result["prompt"].count("素材来源：图片 2") == 2
    assert "左侧人物" in result["prompt"] and "右侧人物" in result["prompt"]


@pytest.mark.parametrize("case", ["foreign", "inactive", "missing"])
def test_invalid_material_is_not_silently_removed(case):
    order, assets, request = example(
        [
            dict(
                target_description="脸",
                change_type="身份",
                instruction="替换",
                source_asset_ids=["a"],
            )
        ]
    )
    if case == "foreign":
        assets[1].order_id = "other"
    elif case == "inactive":
        assets[1].is_active_input = False
    else:
        assets.pop(1)
    with pytest.raises(BusinessError):
        build_initial_prompt(order, assets, request)


def test_old_contract_rejected():
    with pytest.raises(ValidationError):
        Params(hair_source_asset_id="main")
    with pytest.raises(ValidationError):
        InitialInputs(inputs=[{"asset_id": "main", "role": "person_main"}])
