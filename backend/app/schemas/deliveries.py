"""当前交付图选择；最多一张，空列表仅用于明确撤销。"""

from pydantic import Field

from app.schemas.orders import AssetId, StrictModel


class FinalsRequest(StrictModel):
    asset_ids: list[AssetId] = Field(max_length=1)
