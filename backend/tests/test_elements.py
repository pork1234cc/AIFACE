"""动态对象、独立蒙版和版本绑定回归。"""

import numpy as np
import pytest
from pydantic import ValidationError

from app.services.elements import Analysis, encode_mask, validate_analysis


def item(key="left_hair", parent=None):
    return {
        "id": key,
        "parent_id": parent,
        "label": "左侧人物头发",
        "target_description": "画面左侧人物的黑色头发",
        "kind": "part",
        "bbox": [100, 100, 450, 500],
        "positive_points": [[250, 250]],
        "negative_points": [],
    }


def test_dynamic_names_and_distinct_instances():
    data = validate_analysis({"objects": [item(), item("right_hair")]})
    assert len(data.objects) == 2
    data = validate_analysis({"objects": [{**item(), "label": "右下角兔子"}]})
    assert data.objects[0].label == "右下角兔子"


@pytest.mark.parametrize(
    "objects",
    [
        [item(), item()],
        [item(parent="missing")],
        [item("a", "b"), item("b", "a")],
        [{**item(), "bbox": [400, 100, 200, 500]}],
        [{**item(), "positive_points": [[1200, 1]]}],
    ],
)
def test_invalid_object_graph_and_geometry_rejected(objects):
    with pytest.raises((ValueError, ValidationError)):
        validate_analysis({"objects": objects})


def test_empty_analysis_is_valid_without_invented_portrait():
    assert validate_analysis({"objects": []}).objects == []
    assert Analysis.model_json_schema()["additionalProperties"] is False


def test_masks_preserve_holes_and_independent_overlap():
    mask = np.array([[False, True, True], [False, True, False]], dtype=bool)
    assert encode_mask(mask) == [1, 2, 4, 1]
    assert encode_mask(np.zeros((2, 2), dtype=bool)) == []
    assert encode_mask(np.ones((2, 2), dtype=bool)) == [0, 4]


def test_granular_edit_capacity_exceeds_old_twenty_limit():
    from app.schemas.orders import Params

    params = Params(
        region_prompts=[
            {
                "id": f"detail_{i}",
                "label": "细节",
                "target_description": "图片中的细节",
            }
            for i in range(97)
        ]
    )
    assert len(params.region_prompts) == 97


def test_correction_overrides_conflicting_hint_and_can_expand_box():
    from app.services.element_masks import prepare_prompt

    node = validate_analysis({"objects": [item()]}).objects[0]
    points, labels, box = prepare_prompt(node, [[250, 250, 0], [800, 800, 1]])
    paired = list(zip(points, labels, strict=True))
    assert ([250, 250], 1) not in paired
    assert ([250, 250], 0) in paired
    assert box[2] > 800 and box[3] > 800
