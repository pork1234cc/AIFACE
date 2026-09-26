"""元素分析后台任务与持久结果；读取缓存不重复调用 Codex。"""

import hashlib
import json
import logging
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from app.services import codex_elements, element_masks
from app.services.elements import Analysis, validate_analysis
from app.services.orders import BusinessError

logger = logging.getLogger(__name__)
LOCK = Lock()
ACTIVE = Lock()
JOBS: dict[str, dict] = {}


def location(storage: Path, order_id: str, asset_id: str) -> Path:
    return storage / "element-analyses" / order_id / asset_id


def read_result(directory: Path, data: bytes) -> dict | None:
    path = directory / "current.json"
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("image_sha256") == hashlib.sha256(data).hexdigest():
            return result
    except (OSError, ValueError):
        logger.warning("元素识别缓存无法读取")
    return None


def status(directory: Path, data: bytes) -> dict:
    with LOCK:
        job = dict(JOBS.get(str(directory), {}))
    result = read_result(directory, data)
    if job.get("status") in {"running", "failed"}:
        return {**job, "result": result}
    return {"status": "ready" if result else "idle", "result": result}


def save_result(directory: Path, result: dict):
    directory.mkdir(parents=True, exist_ok=True)
    # 每次结果独立留档，current 仅为可恢复指针副本。
    content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    version_file = directory / f"result-{uuid4().hex}.json"
    version_file.write_text(content, encoding="utf-8")
    pending = directory / f"current-{uuid4().hex}.pending"
    pending.write_text(content, encoding="utf-8")
    pending.replace(directory / "current.json")


def build_result(data: bytes, analysis: Analysis, progress=None) -> dict:
    version = uuid4().hex[:12]
    nodes = {node.id: node for node in analysis.objects}
    regions = []
    width, height = 0, 0
    for index, node in enumerate(analysis.objects):
        if progress:
            progress(f"正在定位元素 {index + 1}/{len(analysis.objects)}：{node.label}")
        mask = element_masks.segment(data, node)
        width, height = mask.pop("width"), mask.pop("height")
        mask.pop("image_sha256")
        mask.pop("original_width")
        mask.pop("original_height")
        depth = 0
        parent = node.parent_id
        while parent:
            depth += 1
            parent = nodes[parent].parent_id
        regions.append(
            {
                "id": f"{version}_{node.id}",
                "parent_id": f"{version}_{node.parent_id}" if node.parent_id else None,
                "label": node.label,
                "target_description": node.target_description,
                "origin": "detected",
                "kind": node.kind,
                "depth": depth,
                "bbox": node.bbox,
                "source_id": node.id,
                **mask,
            }
        )
    if not regions:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((1600, 1600))
            width, height = image.size
    # 深度优先输出，使界面中的父对象与所属细节连续排列。
    children: dict[str | None, list] = {}
    for region in regions:
        children.setdefault(region["parent_id"], []).append(region)
    ordered = []

    def visit(parent):
        for child in children.get(parent, []):
            ordered.append(child)
            visit(child["id"])

    visit(None)
    return {
        "schema_version": 1,
        "version": version,
        "provider": "codex+mobile-sam",
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "regions": ordered,
        "width": width,
        "height": height,
        "analysis": analysis.model_dump(),
    }


def public_result(value: dict) -> dict:
    """内部定位提示不进入前端，轮廓与对象层级保留。"""
    result = value.get("result")
    if result:
        value = {**value, "result": {k: v for k, v in result.items() if k != "analysis"}}
    return value


def start(directory: Path, data: bytes, analysis: dict | None = None) -> dict:
    parsed = validate_analysis(analysis) if analysis is not None else None
    with LOCK:
        if JOBS.get(str(directory), {}).get("status") == "running":
            return {"status": "running", "message": "当前图片正在分析"}
        if not ACTIVE.acquire(blocking=False):
            raise BusinessError(409, "element_busy", "正在分析其他图片，请稍后重试")
        # 只保留有限任务状态，结果本身始终落盘。
        if len(JOBS) >= 64:
            JOBS.clear()
        JOBS[str(directory)] = {"status": "running", "message": "Codex 正在分析图片元素"}

    def progress(message):
        with LOCK:
            JOBS[str(directory)] = {"status": "running", "message": message}

    def run():
        try:
            element_masks.sessions()
            selected = parsed or codex_elements.analyze(data, directory / f"run-{uuid4().hex}")
            result = build_result(data, selected, progress)
            save_result(directory, result)
            with LOCK:
                JOBS[str(directory)] = {"status": "ready"}
        except BusinessError as exc:
            with LOCK:
                JOBS[str(directory)] = {"status": "failed", "message": str(exc), "code": exc.code}
        except Exception:
            logger.exception("元素分析失败")
            with LOCK:
                JOBS[str(directory)] = {"status": "failed", "message": "元素分析失败，请重试"}
        finally:
            ACTIVE.release()

    Thread(target=run, daemon=True, name="element-analysis").start()
    return {"status": "running", "message": "正在分析图片元素"}


def refine(directory: Path, data: bytes, region_id: str, version: str, points: list) -> dict:
    if not ACTIVE.acquire(blocking=False):
        raise BusinessError(409, "element_busy", "分析正在进行，请完成后再修正选区")
    try:
        result = read_result(directory, data)
        if not result or result["version"] != version:
            raise BusinessError(409, "element_version_changed", "识别结果已变化，请刷新后修正")
        region = next((r for r in result["regions"] if r["id"] == region_id), None)
        if region is None:
            raise BusinessError(404, "element_not_found", "元素不存在")
        analysis = validate_analysis(result["analysis"])
        node = next(n for n in analysis.objects if n.id == region["source_id"])
        previous = region.get("correction_points", [])
        combined = [*previous, *points]
        if len(combined) > 32:
            raise BusinessError(422, "too_many_points", "该元素修正点已达 32 个，请重新识别")
        mask = element_masks.segment(data, node, combined)
        for key in ("mask_runs", "mask_area", "mask_score", "location_status"):
            region[key] = mask[key]
        region["correction_points"] = combined
        # 修改同一对象轮廓时不改变实例 ID；修订号用于拒绝并发覆盖。
        result["version"] = uuid4().hex[:12]
        save_result(directory, result)
        with LOCK:
            JOBS[str(directory)] = {"status": "ready"}
        return public_result({"status": "ready", "result": result})
    finally:
        ACTIVE.release()
