"""图片解码、受控存储以及当前素材角色管理。"""

import hashlib
import io
import os
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.models.orders import Asset, new_id
from app.services.orders import BusinessError, get_assets, get_order
from app.services.prompts import clear_invalid_sources, refresh_readiness

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


def decode_upload(source: BinaryIO) -> tuple[bytes, str, str, int, int]:
    data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise BusinessError(413, "image_too_large", "单张图片不能超过 20 MiB")
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in FORMATS:
                raise BusinessError(415, "unsupported_image", "仅支持 JPEG、PNG、WebP 图片")
            if picture.width * picture.height > MAX_PIXELS:
                raise BusinessError(413, "too_many_pixels", "图片不能超过 4000 万像素")
            if getattr(picture, "n_frames", 1) != 1:
                raise BusinessError(415, "animated_image", "请上传静态图片，不支持动画或多帧图片")
            extension, mime = FORMATS[picture.format]
            width, height = picture.size
            picture.verify()
        with Image.open(io.BytesIO(data)) as picture:
            picture.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise BusinessError(413, "too_many_pixels", "图片不能超过 4000 万像素") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise BusinessError(415, "invalid_image", "无法读取图片，请确认文件完整且格式正确") from exc
    return data, extension, mime, width, height


def get_input(session: Session, order_id: str, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None or asset.order_id != order_id or asset.kind != "input":
        raise BusinessError(404, "image_not_found", "本订单中不存在该素材")
    return asset


def check_capacity(assets: list[Asset], role: str, *, exclude_id: str | None = None) -> None:
    active = [a for a in assets if a.is_active_input and a.id != exclude_id]
    if len(active) >= 4:
        raise BusinessError(409, "input_limit", "当前素材最多 4 张，请先移出不需要的素材")
    if role in {"person_main", "reference"} and any(a.input_role == role for a in active):
        label = "主照片" if role == "person_main" else "参考图"
        raise BusinessError(409, "role_conflict", f"当前已有{label}，请调整角色后再操作")


def add_asset(
    session: Session,
    storage: Path,
    order_id: str,
    role: str,
    filename: str,
    decoded: tuple[bytes, str, str, int, int],
) -> Asset:
    order = get_order(session, order_id, editable=True)
    assets = get_assets(session, order_id)
    check_capacity(assets, role)
    data, extension, mime, width, height = decoded
    asset_id = new_id()
    relative = Path("orders") / order.id / "inputs" / f"{asset_id}.{extension}"
    target = storage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    # 新 UUID 路径独占创建；异常遗留文件保留，交由明确维护流程处理。
    with temporary.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    temporary.rename(target)
    display_name = filename.replace("\\", "/").split("/")[-1][:255] or f"照片.{extension}"
    asset = Asset(
        id=asset_id,
        order_id=order.id,
        kind="input",
        input_role=role,
        is_active_input=True,
        relative_path=relative.as_posix(),
        original_name=display_name,
        mime_type=mime,
        byte_size=len(data),
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
        sort_index=max((a.sort_index for a in assets), default=-1) + 1,
    )
    session.add(asset)
    session.flush()
    refresh_readiness(order, assets + [asset])
    return asset


def set_role(session: Session, order_id: str, asset_id: str, role: str) -> None:
    order = get_order(session, order_id, editable=True)
    asset = get_input(session, order_id, asset_id)
    assets = get_assets(session, order_id)
    if asset.is_active_input:
        if role == "person_main":
            for previous in assets:
                if (
                    previous.id != asset_id
                    and previous.is_active_input
                    and previous.input_role == role
                ):
                    previous.input_role = "person_aux"
            # 先释放唯一索引，再设置新主照片，仍处于同一写事务。
            session.flush()
        check_capacity(assets, role, exclude_id=asset_id)
    asset.input_role = role
    session.flush()
    clear_invalid_sources(order, assets)


def set_active(session: Session, order_id: str, asset_id: str, active: bool) -> None:
    order = get_order(session, order_id, editable=True)
    asset = get_input(session, order_id, asset_id)
    assets = get_assets(session, order_id)
    if active and not asset.is_active_input:
        check_capacity(assets, asset.input_role, exclude_id=asset_id)
    asset.is_active_input = active
    session.flush()
    clear_invalid_sources(order, assets)


def content_path(storage: Path, asset: Asset) -> Path:
    target = (storage / asset.relative_path).resolve()
    expected = (storage / "orders" / asset.order_id).resolve()
    if not expected.is_relative_to(storage.resolve()) or not target.is_relative_to(expected):
        raise BusinessError(404, "image_not_found", "图片不存在")
    if not target.is_file():
        raise BusinessError(404, "image_file_missing", "图片文件缺失，请检查存储或恢复备份")
    return target
