"""通过 Codex 子进程分析附图；仅接收校验后的结构化最终输出。"""

import json
import os
import subprocess
from pathlib import Path

from app.services.codex_runtime import resolve_executable
from app.services.elements import PROMPT, Analysis, validate_analysis
from app.services.orders import BusinessError


def analyze(data: bytes, directory: Path) -> Analysis:
    executable = resolve_executable()
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / "input.png"
    # 输入转为 PNG，避免文件扩展名与真实编码不一致。
    import io

    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as source:
        picture = ImageOps.exif_transpose(source).convert("RGB")
        picture.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        picture.save(image, format="PNG")
    schema = directory / "analysis.schema.json"
    schema.write_text(
        json.dumps(Analysis.model_json_schema(), ensure_ascii=False), encoding="utf-8"
    )
    output = directory / "analysis.json"
    command = [
        executable,
        "exec",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--output-schema",
        str(schema.resolve()),
        "--output-last-message",
        str(output.resolve()),
        "--image",
        str(image.resolve()),
        "-C",
        str(directory.resolve()),
        "-c",
        'approval_policy="never"',
        "-",
    ]
    environment = os.environ.copy()
    # Codex 推理不需要继承本应用的供应商密钥。
    for key in list(environment):
        if key.lower() in {"image_api", "image_api_url"}:
            environment.pop(key)
    try:
        result = subprocess.run(
            command,
            input=PROMPT,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=360,
            env=environment,
            cwd=directory,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise BusinessError(504, "codex_timeout", "Codex 分析超时，请稍后重试") from exc
    except OSError as exc:
        raise BusinessError(
            503, "codex_unavailable", "无法启动 Codex，请检查安装和登录状态"
        ) from exc
    if result.returncode != 0 or not output.is_file():
        # 不向页面或日志输出可能含凭据、路径、环境信息的 CLI stderr。
        raise BusinessError(503, "codex_failed", "Codex 分析失败，请检查 CLI 登录和模型可用性")
    if output.stat().st_size > 256_000:
        raise BusinessError(502, "codex_invalid_output", "Codex 返回数据过大")
    try:
        return validate_analysis(json.loads(output.read_text(encoding="utf-8")))
    except (ValueError, OSError) as exc:
        raise BusinessError(
            502, "codex_invalid_output", "Codex 对象结构或坐标不合法，请重试"
        ) from exc
