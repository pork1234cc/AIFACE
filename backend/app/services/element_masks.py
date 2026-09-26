"""MobileSAM 的本地轮廓定位，保留原图比例并缓存最近一张图的编码。"""

import hashlib
import io
from functools import lru_cache
from threading import Lock

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

from app.config import PROJECT_ROOT
from app.services.elements import Element, encode_mask
from app.services.orders import BusinessError

LOCK = Lock()
MODEL_ROOT = PROJECT_ROOT / "storage/models/mobile-sam"


@lru_cache(maxsize=1)
def sessions():
    paths = [MODEL_ROOT / "mobile_sam.encoder.onnx", MODEL_ROOT / "sam_vit_h_4b8939.decoder.onnx"]
    if not all(path.is_file() for path in paths):
        raise BusinessError(
            503, "element_model_missing", "请先运行 scripts/install-element-model.py"
        )
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    return tuple(
        ort.InferenceSession(str(p), options, providers=["CPUExecutionProvider"]) for p in paths
    )


@lru_cache(maxsize=1)
def encode_image(data: bytes):
    encoder, _ = sessions()
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        original_size = image.size
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        width, height = image.size
        scale = 1024 / max(width, height)
        resized = (int(width * scale + 0.5), int(height * scale + 0.5))
        pixels = np.asarray(image.resize(resized, Image.Resampling.BILINEAR), dtype=np.float32)
    embedding = encoder.run(None, {"input_image": pixels})[0]
    return embedding, (width, height), resized, original_size


def prepare_prompt(node: Element, extra_points: list[list[float]] | None):
    points = [*node.positive_points, *node.negative_points]
    labels = [1] * len(node.positive_points) + [0] * len(node.negative_points)
    x1, y1, x2, y2 = node.bbox
    for x, y, label in extra_points or []:
        # 人工修正优先，去掉同一位置附近的相反旧提示。
        retained = [
            (p, old)
            for p, old in zip(points, labels, strict=True)
            if old == label or (p[0] - x) ** 2 + (p[1] - y) ** 2 > 12**2
        ]
        points = [p for p, _ in retained] + [[x, y]]
        labels = [old for _, old in retained] + [label]
        if label == 1:
            x1, y1 = min(x1, max(0, x - 10)), min(y1, max(0, y - 10))
            x2, y2 = max(x2, min(1000, x + 10)), max(y2, min(1000, y + 10))
    points += [[x1, y1], [x2, y2]]
    labels += [2, 3]
    return points, labels, [x1, y1, x2, y2]


def segment(data: bytes, node: Element, extra_points: list[list[float]] | None = None) -> dict:
    """归一化提示点与框交给 SAM；返回独立前景 RLE，不用框冒充轮廓。"""
    with LOCK:
        embedding, (width, height), (rw, rh), original = encode_image(data)
        _, decoder = sessions()
        points, labels, (x1, y1, x2, y2) = prepare_prompt(node, extra_points)
        coords = np.asarray(points, dtype=np.float32) * np.array([rw, rh], np.float32) / 1000
        outputs = decoder.run(
            None,
            {
                "image_embeddings": embedding,
                "point_coords": coords[None],
                "point_labels": np.asarray([labels], dtype=np.float32),
                "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32),
                "has_mask_input": np.zeros(1, dtype=np.float32),
                "orig_im_size": np.array([1024, 1024], dtype=np.float32),
            },
        )
        # 导出的解码器包含固定裁切参数，使用低分辨率 logits 自行还原长宽比。
        logits = Image.fromarray(outputs[2][0, 0]).resize((1024, 1024), Image.Resampling.BILINEAR)
        logits = logits.crop((0, 0, rw, rh)).resize((width, height), Image.Resampling.BILINEAR)
        mask = np.asarray(logits) > 0
        area = int(mask.sum())
        score = float(outputs[1].ravel()[0])
        valid = area >= 4 and np.isfinite(score) and score >= 0.45
        # 极端越界通常代表选中了其他对象，保留列表候选供修正。
        box_area = (x2 - x1) * (y2 - y1) * width * height / 1_000_000
        valid = valid and area <= max(16, box_area * 2)
        return {
            "mask_runs": encode_mask(mask) if valid else [],
            "mask_area": area if valid else 0,
            "mask_score": round(score, 3) if np.isfinite(score) else 0,
            "location_status": "located" if valid else "unlocated",
            "width": width,
            "height": height,
            "original_width": original[0],
            "original_height": original[1],
            "image_sha256": hashlib.sha256(data).hexdigest(),
        }
