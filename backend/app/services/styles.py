"""固定风格从本地受控配置加载，不隐式附加示例图。"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import PROJECT_ROOT
from app.services.orders import BusinessError


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_style: str
    subject_rule: str
    render_rule: str
    negative_rule: str


class Style(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style_id: Literal["q_crayon_001"]
    style_name: str
    version: str
    status: Literal["active"]
    cover_image: None
    reference_images: list[str]
    background: Literal["white"]
    aspect_ratio: Literal["1:1"]
    initial_count: Literal[1]
    revision_count: Literal[1]
    allowed_controls: list[str]
    prompt_template: PromptTemplate
    qa_checklist: list[str]


def load_style(style_id: str = "q_crayon_001") -> Style:
    if style_id != "q_crayon_001":
        raise BusinessError(404, "style_not_found", "风格不存在")
    with (PROJECT_ROOT / "styles/q_crayon_001/style.json").open(encoding="utf-8") as source:
        return Style.model_validate(json.load(source))
