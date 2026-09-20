"""订单写入契约；拒绝未知字段，防止悄悄忽略无效控制项。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Role = Literal["person_main", "person_aux", "reference"]
OrderStatus = Literal["draft", "ready", "review", "revision_requested", "completed", "closed"]
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


class Params(StrictModel):
    hair_source_asset_id: AssetId | None = None
    glasses_keep: bool = True
    clothes_mode: Literal["person", "reference", "simplified"] = "simplified"
    clothes_source_asset_id: AssetId | None = None
    background: Literal["white"] = "white"
    aspect_ratio: Literal["1:1"] = "1:1"
    extra_requirement: Note = ""


class RolePatch(StrictModel):
    role: Role


class ActivePatch(StrictModel):
    active: bool


class InputItem(StrictModel):
    asset_id: AssetId
    role: Role


class InitialInputs(StrictModel):
    inputs: list[InputItem] = Field(min_length=1, max_length=4)
