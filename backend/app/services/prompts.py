"""统一底图配置校验与提示词；预览和提交共用。"""

import re

from sqlalchemy.orm import Session

from app.models.orders import Asset, Order, utc_now
from app.schemas.orders import InitialInputs, Params
from app.services.orders import BusinessError
from app.services.styles import load_style


def validate_sources(params: Params, assets: list[Asset]) -> None:
    active = {a.id: a for a in assets if a.kind == "input" and a.is_active_input}
    ids = {key for change in params.changes for key in change.source_asset_ids}
    if params.material_slots is not None:
        if params.changes:
            raise BusinessError(422, "mixed_instructions", "请将逐项修改合并到额外提示词")
        supplied = [key for key in params.material_slots if key]
        if len(supplied) != len(set(supplied)):
            raise BusinessError(422, "duplicate_material", "不同素材位置不能重复引用同一图片")
        ids = set(supplied)
        for match in re.finditer(
            r"素材(?:图)?\s*([1-9][0-9]*|[一二三四五六七八九十])", params.extra_requirement
        ):
            token = match.group(1)
            number = int(token) if token.isdigit() else "一二三四五六七八九十".index(token) + 1
            if number > len(params.material_slots) or params.material_slots[number - 1] is None:
                raise BusinessError(422, "missing_material", f"提示词引用的素材{number}尚未上传")
    for key in ids:
        if key not in active or active[key].input_role != "material":
            raise BusinessError(
                422, "invalid_source", "素材引用缺失、已移出或不属于本单素材图，请重新选择"
            )
    seen = {}
    for change in params.changes:
        key = (change.target_description, change.change_type)
        value = (change.instruction, tuple(change.source_asset_ids), change.preserve_instruction)
        if key in seen and seen[key] != value:
            raise BusinessError(
                422, "conflicting_changes", "同一对象同一用途存在不同要求，请合并澄清后提交"
            )
        seen[key] = value


def readiness_errors(params: Params, assets: list[Asset]) -> list[str]:
    errors = []
    base = next((a for a in assets if a.id == params.base_asset_id), None)
    if base is None or (
        base.kind == "input" and (not base.is_active_input or base.input_role != "main")
    ):
        errors.append("请明确选择本次编辑底图")
    try:
        validate_sources(params, assets)
    except BusinessError as exc:
        errors.append(exc.message)
    return errors


def refresh_readiness(order: Order, assets: list[Asset]) -> list[str]:
    errors = readiness_errors(Params.model_validate(order.params_json), assets)
    # 输入是否齐备由 readiness 单独表达；提交任务前订单一直处于待整理。
    order.updated_at = utc_now()
    return errors


def clear_invalid_sources(order: Order, assets: list[Asset]) -> None:
    # 保留失效引用供用户修正，禁止静默丢弃修改关系。
    refresh_readiness(order, assets)


def build_initial_prompt(
    order: Order, assets: list[Asset], payload: InitialInputs, session: Session | None = None
) -> dict:
    if order.status in {"completed", "closed"}:
        raise BusinessError(409, "order_readonly", "已完成或关闭的订单只读")
    params = payload.config
    assets = [a for a in assets if a.order_id == order.id]
    errors = readiness_errors(params, assets)
    if errors:
        raise BusinessError(422, "order_not_ready", "；".join(errors))
    ids = list(dict.fromkeys(key for change in params.changes for key in change.source_asset_ids))
    if params.material_slots is not None:
        ids = [key for key in params.material_slots if key]
    inputs = [{"asset_id": params.base_asset_id, "role": "base"}] + [
        {"asset_id": key, "role": "material"} for key in ids
    ]
    positions = {item["asset_id"]: i + 1 for i, item in enumerate(inputs)}
    style = (
        load_style(params.style_id, session).model_dump()
        if params.style_id
        else {
            "style_id": None,
            "version": "original",
            "prompt_template": {},
        }
    )
    lines = [
        "图片 1 是本次编辑底图。未明确要求修改的内容默认保留。",
        "保留底图的人物和物品数量、位置、姿态、背景及布局；画面左右均以观看者视角为准。",
        "明确修改要求可以覆盖对应默认保留规则；修改手势仅可自然衔接邻近手腕及必要局部手臂。",
        *[
            f"图片 {positions[key]} 是素材，仅提供下列明确指定元素。"
            "未明确指定时，不迁移背景、服装或其他人物特征。"
            for key in ids
        ],
    ]
    for i, change in enumerate(params.changes, 1):
        sources = (
            "、".join(f"图片 {positions[key]}" for key in dict.fromkeys(change.source_asset_ids))
            or "无（文字修改）"
        )
        lines.append(
            f"修改 {i}：目标：{change.target_description}；用途：{change.change_type}；"
            f"素材来源：{sources}；要求：{change.instruction}；"
            f"保留：{change.preserve_instruction or '未指定修改的内容'}"
        )
    if params.material_slots is not None:
        lines.extend(
            f"素材{slot} 对应图片 {positions[key]}。"
            for slot, key in enumerate(params.material_slots, 1)
            if key
        )
        lines.append(
            "素材编号固定，与图片输入序号不同。按补充要求指定的用途使用素材；"
            "未指明用途的素材不主动应用，不自行推断替换对象。"
        )
    lines.extend(
        style["prompt_template"].values() if params.style_id else ["保持底图原有表现风格。"]
    )
    lines += [
        f"补充要求及取景：{params.extra_requirement or '保留原图取景意图'}",
        f"只输出一张独立图片，画布比例 {params.aspect_ratio}；"
        "比例不等于取景要求，不拉伸人物或物品。",
    ]
    return {
        "inputs": inputs,
        "params": params.model_dump(),
        "style": style,
        "prompt": "\n".join(lines),
        "target_count": 1,
    }
