"""来源图片须进入实际输入，提示词准确引用有序图片。"""

import pytest

from app.models.orders import Asset, Order, default_params
from app.schemas.orders import InitialInputs, Params
from app.services.orders import BusinessError
from app.services.prompts import build_initial_prompt, clear_invalid_sources, readiness_errors


def example():
    order = Order(id="order", style_id="q_crayon_001", status="draft", params_json=default_params())
    assets = [
        Asset(
            id="main",
            order_id="order",
            kind="input",
            input_role="person_main",
            is_active_input=True,
        ),
        Asset(
            id="aux", order_id="order", kind="input", input_role="person_aux", is_active_input=True
        ),
        Asset(
            id="ref", order_id="order", kind="input", input_role="reference", is_active_input=True
        ),
    ]
    order.params_json |= {
        "hair_source_asset_id": "aux",
        "clothes_mode": "reference",
        "clothes_source_asset_id": "ref",
    }
    return order, assets


def payload(assets):
    return InitialInputs(inputs=[{"asset_id": a.id, "role": a.input_role} for a in assets])


def test_prompt_references_real_input_order():
    order, assets = example()
    result = build_initial_prompt(order, assets, payload(list(reversed(assets))))
    assert "本人主照片：图片 3" in result["prompt"]
    assert "发型来源：图片 2" in result["prompt"]
    assert "服装取自图片 1" in result["prompt"]
    assert result["target_count"] == 1
    assert "只输出一张独立" in result["prompt"]
    assert result["style"]["reference_images"] == []
    assert len(result["inputs"]) == 3


@pytest.mark.parametrize(
    "case", ["missing_source", "foreign", "duplicate", "wrong_role", "no_main"]
)
def test_invalid_initial_input(case):
    order, assets = example()
    selected = payload(assets)
    if case == "missing_source":
        selected.inputs.pop()
    elif case == "foreign":
        assets[0].order_id = "another"
    elif case == "duplicate":
        selected.inputs.append(selected.inputs[0])
    elif case == "wrong_role":
        selected.inputs[0].role = "reference"
    else:
        selected.inputs.pop(0)
    with pytest.raises(BusinessError):
        build_initial_prompt(order, assets, selected)


def test_deactivation_clears_only_current_source():
    order, assets = example()
    snapshot = dict(order.params_json)
    assets[2].is_active_input = False
    clear_invalid_sources(order, assets)
    assert order.params_json["clothes_source_asset_id"] is None
    assert order.params_json["clothes_mode"] == "reference"
    assert order.params_json["hair_source_asset_id"] == "aux"
    assert order.status == "draft"
    assert snapshot["clothes_source_asset_id"] == "ref"
    assert readiness_errors(Params.model_validate(order.params_json), assets)
