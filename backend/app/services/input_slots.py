"""固定图片位置的事务更新；移出仅停用资产，保留历史文件。"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.schemas.orders import Params
from app.services.assets import add_asset
from app.services.generation import ensure_available
from app.services.orders import BusinessError, get_assets, get_order
from app.services.prompts import refresh_readiness


def update_slot(
    session: Session,
    storage: Path,
    order_id: str,
    slot: str,
    filename: str = "",
    decoded: tuple[bytes, str, str, int, int] | None = None,
) -> None:
    if slot != "main" and (
        not slot.isascii() or not slot.isdecimal() or len(slot) > 9 or int(slot) < 1
    ):
        raise BusinessError(422, "invalid_slot", "图片位置必须是主图片或正整数素材编号")
    ensure_available(session, order_id)
    order = get_order(session, order_id, editable=True)
    assets = get_assets(session, order_id)
    params = Params.model_validate(order.params_json)
    active = [a for a in assets if a.kind == "input" and a.is_active_input]
    slots = (
        list(params.material_slots)
        if params.material_slots is not None
        else [a.id for a in active if a.input_role == "material"]
    )
    slots.extend([None] * max(0, 3 - len(slots)))
    if slot != "main":
        number = int(slot)
        if number > len(slots) + 1:
            raise BusinessError(422, "invalid_slot", "请按顺序添加素材位置")
        if number == len(slots) + 1:
            slots.append(None)
    main = next((a for a in active if a.input_role == "main"), None)
    previous_id = (main.id if main else None) if slot == "main" else slots[int(slot) - 1]
    previous = next((a for a in active if a.id == previous_id), None)
    if previous:
        previous.is_active_input = False
        session.flush()
    replacement = (
        add_asset(
            session, storage, order_id, "main" if slot == "main" else "material", filename, decoded
        )
        if decoded
        else None
    )
    if slot == "main":
        if params.base_asset_id is None or params.base_asset_id == previous_id:
            params.base_asset_id = replacement.id if replacement else None
    else:
        slots[int(slot) - 1] = replacement.id if replacement else None
    # 旧结构化配置由前端转为文字后再保存；此时先保留，避免静默丢失要求。
    params.material_slots = slots
    order.params_json = params.model_dump()
    refresh_readiness(order, get_assets(session, order_id))
