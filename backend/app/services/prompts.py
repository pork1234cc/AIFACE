"""当前参数与实际输入校验；首次生成一张交付图。"""

from app.models.orders import Asset, Order, utc_now
from app.schemas.orders import InitialInputs, Params
from app.services.orders import BusinessError
from app.services.styles import load_style


def validate_sources(params: Params, assets: list[Asset]) -> None:
    active = {a.id: a for a in assets if a.kind == "input" and a.is_active_input}
    if params.hair_source_asset_id is not None:
        hair = active.get(params.hair_source_asset_id)
        if hair is None or hair.input_role not in {"person_main", "person_aux"}:
            raise BusinessError(422, "invalid_hair_source", "发型来源须为本单当前主照片或辅助照片")
    source = active.get(params.clothes_source_asset_id)
    if params.clothes_mode == "simplified":
        if params.clothes_source_asset_id is not None:
            raise BusinessError(422, "invalid_clothes_source", "简化服装时不应指定来源图片")
    elif params.clothes_source_asset_id is not None:
        roles = (
            {"reference"} if params.clothes_mode == "reference" else {"person_main", "person_aux"}
        )
        if source is None or source.input_role not in roles:
            raise BusinessError(422, "invalid_clothes_source", "服装来源须属于本单且符合所选模式")
    else:
        raise BusinessError(422, "missing_clothes_source", "请为服装模式选择来源图片")


def readiness_errors(params: Params, assets: list[Asset]) -> list[str]:
    active = [a for a in assets if a.kind == "input" and a.is_active_input]
    errors = []
    if not 1 <= len(active) <= 4:
        errors.append("当前素材需要 1～4 张")
    if sum(a.input_role == "person_main" for a in active) != 1:
        errors.append("请选择一张主照片")
    if sum(a.input_role == "reference" for a in active) > 1:
        errors.append("参考图最多一张")
    if params.hair_source_asset_id is None:
        errors.append("请选择发型来源")
    try:
        validate_sources(params, active)
    except BusinessError as exc:
        errors.append(exc.message)
    return errors


def refresh_readiness(order: Order, assets: list[Asset]) -> list[str]:
    errors = readiness_errors(Params.model_validate(order.params_json), assets)
    if order.status in {"draft", "ready"}:
        order.status = "draft" if errors else "ready"
    order.updated_at = utc_now()
    return errors


def clear_invalid_sources(order: Order, assets: list[Asset]) -> None:
    params = Params.model_validate(order.params_json)
    active = {a.id: a for a in assets if a.is_active_input and a.kind == "input"}
    hair = active.get(params.hair_source_asset_id)
    if hair is None or hair.input_role not in {"person_main", "person_aux"}:
        params.hair_source_asset_id = None
    clothes = active.get(params.clothes_source_asset_id)
    roles = {"reference"} if params.clothes_mode == "reference" else {"person_main", "person_aux"}
    if clothes is None or clothes.input_role not in roles:
        # 保留原服装模式，让详情明确提示重新选择；不静默改为简化服装。
        params.clothes_source_asset_id = None
    order.params_json = params.model_dump()
    refresh_readiness(order, assets)


def build_initial_prompt(order: Order, assets: list[Asset], payload: InitialInputs) -> dict:
    if order.status in {"completed", "closed"}:
        raise BusinessError(409, "order_readonly", "已完成或关闭的订单只读")
    by_id = {a.id: a for a in assets if a.order_id == order.id and a.is_active_input}
    ids = [item.asset_id for item in payload.inputs]
    if len(set(ids)) != len(ids):
        raise BusinessError(422, "duplicate_input", "输入图片不能重复")
    selected = []
    for item in payload.inputs:
        asset = by_id.get(item.asset_id)
        if asset is None or asset.kind != "input" or asset.input_role != item.role:
            raise BusinessError(422, "invalid_input", "输入图片须属于本单当前素材且角色一致")
        selected.append(asset)
    params = Params.model_validate(order.params_json)
    errors = readiness_errors(params, selected)
    if errors:
        raise BusinessError(422, "order_not_ready", "；".join(errors))
    style = load_style(order.style_id)
    positions = {asset.id: index + 1 for index, asset in enumerate(selected)}
    main = next(asset for asset in selected if asset.input_role == "person_main")
    clothes = "简化服装，保持整体协调"
    if params.clothes_mode != "simplified":
        clothes = f"服装取自图片 {positions[params.clothes_source_asset_id]}"
    prompt = "\n".join(
        [
            "请根据以下有序输入生成一张单人头像插画。",
            style.prompt_template.system_style,
            style.prompt_template.subject_rule,
            f"本人主照片：图片 {positions[main.id]}。",
            f"发型来源：图片 {positions[params.hair_source_asset_id]}。",
            "眼镜：" + ("保留原有眼镜。" if params.glasses_keep else "去掉眼镜。"),
            clothes + "。",
            f"额外要求：{params.extra_requirement or '无'}",
            style.prompt_template.render_rule,
            style.prompt_template.negative_rule,
        ]
    )
    return {
        "inputs": payload.model_dump()["inputs"],
        "params": params.model_dump(),
        "style": style.model_dump(),
        "prompt": prompt,
        "target_count": 1,
    }
