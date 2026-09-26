"""下载固定摘要的 MobileSAM ONNX 模型；已有文件保留。"""

import hashlib
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parents[1] / "storage/models/mobile-sam"
URL = (
    "https://huggingface.co/vietanhdev/segment-anything-onnx-models/"
    "resolve/main/mobile_sam_20230629.zip"
)
SHA256 = "41aff2660b7531becfee21fb257c49933ddc892c554507bdb775bf504d443942"


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / "mobile_sam_20230629.zip"
    if not archive.exists():
        print("下载 MobileSAM（约 35 MiB），不上传照片。", flush=True)
        with urlopen(URL, timeout=60) as response, archive.open("xb") as target:
            while block := response.read(1024 * 1024):
                target.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("下载文件摘要不匹配，原文件已保留，请检查下载情况")
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if not entry.filename.endswith(".onnx"):
                continue
            # 只取文件名，不沿用归档内路径。
            destination = ROOT / Path(entry.filename).name
            content = bundle.read(entry)
            if destination.exists():
                if destination.read_bytes() != content:
                    raise RuntimeError("已有模型内容不同，保留原文件")
            else:
                with destination.open("xb") as output:
                    output.write(content)
            print(f"模型已校验：{destination.name}")


if __name__ == "__main__":
    main()
