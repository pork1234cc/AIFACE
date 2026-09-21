"""生成恢复请求，禁止未定义字段和隐式风险确认。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.schemas.orders import InitialInputs, StrictModel


class RevisionRequest(InitialInputs):
    pass


class ReviewRequest(StrictModel):
    review_status: Literal["unreviewed", "selected", "discarded"]


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_indices: list[StrictInt] = Field(min_length=1, max_length=1)


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["link_remote_task", "confirm_not_accepted", "resubmit_with_risk"]
    note: str = Field(min_length=5, max_length=1000)
    provider_task_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    acknowledge_possible_duplicate_charge: StrictBool = False
