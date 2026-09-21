"""默认保留、明确覆盖、冲突与失效引用的边界。"""

import pytest
from test_unified_creation import example

from app.schemas.orders import Params
from app.services.orders import BusinessError
from app.services.prompts import build_initial_prompt, clear_invalid_sources, readiness_errors


def test_original_style_and_crop():
    order, assets, payload = example()
    payload.config.style_id = None
    payload.config.aspect_ratio = "3:4"
    payload.config.extra_requirement = "裁掉手部，保留面部和发型"
    result = build_initial_prompt(order, assets, payload)
    assert "保持底图原有表现风格" in result["prompt"]
    assert "裁掉手部" in result["prompt"]
    assert "3:4" in result["prompt"]
    assert result["style"]["style_id"] is None


def test_conflicting_same_target_requires_clarification():
    changes = [
        dict(target_description="左侧人物", change_type="眼镜", instruction=text)
        for text in ["保留眼镜", "去掉眼镜"]
    ]
    with pytest.raises(BusinessError, match="澄清"):
        build_initial_prompt(*example(changes))


def test_deactivation_preserves_reference_for_explicit_correction():
    order, assets, _ = example(
        [
            dict(
                target_description="脸",
                change_type="身份",
                instruction="替换",
                source_asset_ids=["a"],
            )
        ]
    )
    assets[1].is_active_input = False
    clear_invalid_sources(order, assets)
    assert order.params_json["changes"][0]["source_asset_ids"] == ["a"]
    assert order.status == "draft"
    assert readiness_errors(Params.model_validate(order.params_json), assets)


def test_missing_base_rejected():
    order, assets, payload = example()
    payload.config.base_asset_id = None
    with pytest.raises(BusinessError):
        build_initial_prompt(order, assets, payload)
