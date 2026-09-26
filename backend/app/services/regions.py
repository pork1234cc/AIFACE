"""本地人像语义识别；蒙版只供界面定位，不参与生图请求。"""

import base64
import io
import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image

from app.config import PROJECT_ROOT
from app.services.orders import BusinessError

MODEL_PATH = PROJECT_ROOT / "storage/models/face-parsing/resnet18.onnx"
INFERENCE_LOCK = Lock()
logger = logging.getLogger(__name__)

# 合并左右五官，避免模型的人体左右与界面的画面左右混淆。
REGIONS = [
    ("hair", "头发", (17,)),
    ("eyes", "眼睛", (4, 5)),
    ("brows", "眉毛", (2, 3)),
    ("lips", "嘴唇与嘴部", (11, 12, 13)),
    ("face", "面部皮肤", (1,)),
    ("nose", "鼻子", (10,)),
    ("ears", "耳朵", (7, 8)),
    ("neck", "颈部", (14,)),
    ("clothes", "服饰", (16,)),
    ("glasses", "眼镜", (6,)),
    ("earrings", "耳饰", (9,)),
    ("necklace", "项链", (15,)),
    ("hat", "帽子", (18,)),
    ("background", "背景", (0,)),
]


@lru_cache(maxsize=1)
def model_session(path: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    return ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])


def summarize_mask(labels: np.ndarray) -> dict:
    """返回候选区域与小尺寸索引图；索引零表示未纳入候选的像素。"""
    mask = np.zeros(labels.shape, dtype=np.uint8)
    regions = []
    for index, (key, label, classes) in enumerate(REGIONS, 1):
        selected = np.isin(labels, classes)
        if int(selected.sum()) < 32:
            continue
        mask[selected] = index
        regions.append(
            {
                "id": key,
                "label": label,
                "target_description": label,
                "origin": "detected",
                "mask_value": index,
            }
        )
    if not any(region["id"] == "face" for region in regions):
        raise BusinessError(422, "portrait_not_found", "未识别到清晰人像，可手动添加区域")
    buffer = io.BytesIO()
    # RGB 三通道相同，浏览器读取红通道即可取得区域索引。
    Image.fromarray(mask).convert("RGB").save(buffer, format="PNG")
    return {
        "regions": regions,
        "mask_url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"),
        "width": labels.shape[1],
        "height": labels.shape[0],
    }


def recognize_regions(data: bytes, model_path: Path | None = None) -> dict:
    path = model_path or MODEL_PATH
    if not path.is_file():
        raise BusinessError(
            503,
            "region_model_unavailable",
            "本地区域识别模型未安装，请先运行模型安装脚本；也可手动添加区域",
        )
    if not INFERENCE_LOCK.acquire(blocking=False):
        raise BusinessError(409, "region_model_busy", "本地识别正在处理其他照片，请稍后重试")
    try:
        with Image.open(io.BytesIO(data)) as image:
            rgb = image.convert("RGB").resize((512, 512), Image.Resampling.BILINEAR)
        pixels = np.asarray(rgb, dtype=np.float32) / 255.0
        pixels = (pixels - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        session = model_session(str(path.resolve()))
        output = session.run(
            None, {session.get_inputs()[0].name: pixels.transpose(2, 0, 1)[None].copy()}
        )[0]
        if output.shape != (1, 19, 512, 512) or not np.isfinite(output).all():
            raise ValueError("区域模型输出异常")
        return summarize_mask(output[0].argmax(axis=0).astype(np.uint8))
    except BusinessError:
        raise
    except Exception as exc:
        # 隔离推理运行时错误，不向客户端暴露本地路径和第三方堆栈。
        logger.exception("本地区域识别失败")
        raise BusinessError(
            503, "region_inference_failed", "本地区域识别失败，可重试或手动添加区域"
        ) from exc
    finally:
        INFERENCE_LOCK.release()
