"""独立调用 Codex 分析图片，输出可导入元素接口的 JSON。"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from app.config import PROJECT_ROOT
from app.services.codex_elements import analyze
from app.services.elements import Analysis, validate_analysis


def main():
    parser = argparse.ArgumentParser(description="Codex 图片元素分析与结果导出")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--analysis", type=Path, help="已有 Codex JSON；提供时不重复调用模型"
    )
    parser.add_argument("--schema", type=Path, help="仅导出 Codex output-schema")
    args = parser.parse_args()
    if args.schema:
        content = Analysis.model_json_schema()
        destination = args.schema
    else:
        if not args.image or not args.output:
            parser.error("需要 --image 和 --output；或单独使用 --schema")
        if args.output.exists():
            parser.error("输出文件已存在，请使用新路径，避免覆盖")
        data = args.image.read_bytes()
        if args.analysis:
            result = validate_analysis(
                json.loads(args.analysis.read_text(encoding="utf-8"))
            )
        else:
            directory = PROJECT_ROOT / "storage/element-runs" / uuid4().hex
            result = analyze(data, directory)
        content = {
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "analysis": result.model_dump(),
        }
        destination = args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as output:
        json.dump(content, output, ensure_ascii=False, indent=2)
    print(f"已写入：{destination.resolve()}")


if __name__ == "__main__":
    main()
