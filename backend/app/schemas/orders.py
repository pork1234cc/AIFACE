"""订单写入契约；拒绝未知字段，防止悄悄忽略无效控制项。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
    base_asset_id: AssetId | None = None
    style_id: (
        Annotated[str, StringConstraints(pattern=r"^(q_crayon_001|custom_[0-9a-f]{32})$")] | None
    ) = "q_crayon_001"
    changes: list[ChangeItem] = Field(default_factory=list, max_length=20)
    region_asset_id: AssetId | None = None
    region_prompts: list[RegionPrompt] = Field(default_factory=list, max_length=20)
    material_slots: list[AssetId | None] | None = Field(default=None, min_length=3)
    aspect_ratio: Literal[
        "16:9", "21:9", "4:3", "3:2", "5:4", "1:1", "4:5", "2:3", "3:4", "9:16", "9:21"
    ] = "1:1"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    extra_requirement: Note = ""


class RolePatch(StrictModel):
    role: Role


class ActivePatch(StrictModel):
    active: bool


class InputItem(StrictModel):
    asset_id: AssetId
    role: Role


class InitialInputs(StrictModel):
    config: Params
