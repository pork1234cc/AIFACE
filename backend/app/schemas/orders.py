"""订单写入契约；拒绝未知字段，防止悄悄忽略无效控制项。"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Role = Literal["main", "material"]
OrderStatus = Literal["draft", "generating", "modifying", "review", "completed", "closed"]
CustomerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
AssetId = Annotated[str, StringConstraints(min_length=1, max_length=36)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OrderCreate(StrictModel):
    customer_name: CustomerName
    note: Note = ""


class OrderPatch(StrictModel):
    customer_name: CustomerName = Field(default="", validate_default=False)
    note: Note = ""


class ChangeItem(StrictModel):
    target_description: CustomerName
    change_type: CustomerName
    source_asset_ids: list[AssetId] = Field(default_factory=list)
    instruction: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    preserve_instruction: Note = ""


class RegionPrompt(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    label: CustomerName
    target_description: CustomerName
    origin: Literal["detected", "manual"] = "manual"
    source_asset_ids: list[AssetId] = Field(default_factory=list, max_length=100)
    instruction: Note = ""
    preserve_instruction: Note = ""


class Params(StrictModel):
    schema_version: Literal[2] = 2
    mode: Literal["edit", "generate"] = "edit"
    base_asset_id: AssetId | None = None
    style_id: (
        Annotated[str, StringConstraints(pattern=r"^(q_crayon_001|custom_[0-9a-f]{32})$")] | None
    ) = "q_crayon_001"
    changes: list[ChangeItem] = Field(default_factory=list, max_length=20)
    region_asset_id: AssetId | None = None
    region_prompts: list[RegionPrompt] = Field(default_factory=list, max_length=100)
    material_slots: list[AssetId | None] | None = Field(default=None, min_length=3)
    aspect_ratio: str = Field(default="1:1", max_length=25)
    size: str | None = Field(default=None, max_length=20)
    response_format: Literal["url", "b64_json"] = "url"
    async_mode: bool = True
    mask: str | None = Field(default=None, max_length=28_000_000, repr=False)
    mask_base_asset_id: AssetId | None = None
    output_format: Literal["png", "jpeg", "webp"] = "png"
    extra_requirement: Note = ""

    @field_validator("aspect_ratio")
    @classmethod
    def validate_ratio(cls, value: str) -> str:
        if value == "":
            return value
        if not re.fullmatch(r"[1-9][0-9]{0,11}:[1-9][0-9]{0,11}", value):
            raise ValueError("比例须为正整数 n:m")
        width, height = map(int, value.split(":"))
        if max(width, height) > 3 * min(width, height):
            raise ValueError("长短边比例不能超过 3:1")
        return value

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"[1-9][0-9]{0,3}x[1-9][0-9]{0,3}", value):
            raise ValueError("尺寸须为宽x高，例如 1024x1024")
        width, height = map(int, value.split("x"))
        if width % 16 or height % 16 or max(width, height) > 3 * min(width, height):
            raise ValueError("尺寸须为16的倍数，长短边比≤3；尺寸上限由所选模型决定")
        return value


class RolePatch(StrictModel):
    role: Role


class ActivePatch(StrictModel):
    active: bool


class InputItem(StrictModel):
    asset_id: AssetId
    role: Role


class InitialInputs(StrictModel):
    config: Params
