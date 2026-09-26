"""安装已固定摘要的本地区域模型，不覆盖已有文件。"""

import hashlib
import sys
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

MODEL_URL = (
    "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx"
)
MODEL_SHA256 = "0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f"
DESTINATION = (
    Path(__file__).resolve().parents[1] / "storage/models/face-parsing/resnet18.onnx"
)


def main():
    if DESTINATION.exists():
        if hashlib.sha256(DESTINATION.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("已有模型校验失败，原文件已保留，请检查后再安装")
        print("本地区域模型已安装，SHA256 校验通过。")
        return
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(f".{uuid4().hex}.download")
    digest = hashlib.sha256()
    print("正在下载本地区域模型（约 51 MiB），不会上传照片。")
    with urlopen(MODEL_URL, timeout=60) as response, temporary.open("xb") as target:
        while block := response.read(1024 * 1024):
            digest.update(block)
            target.write(block)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError(f"模型摘要不匹配，下载文件保留于 {temporary}")
    # Windows rename 不覆盖目标，避免并行安装覆盖已有模型。
    temporary.rename(DESTINATION)
    print("本地区域模型安装完成，SHA256 校验通过。")


if __name__ == "__main__":
    main()
