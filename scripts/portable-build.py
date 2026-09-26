"""便携构建的宿主步骤；产物按哈希登记，清理采用可恢复归档。"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from datetime import datetime
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".commenlib-build"
POINTER = ROOT / "outputs/portable-build-current.json"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def save(record):
    (Path(record["record_dir"]) / "manifest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load():
    record_dir = Path(json.loads(POINTER.read_text(encoding="utf-8"))["record_dir"])
    return json.loads((record_dir / "manifest.json").read_text(encoding="utf-8"))


def run(args, **kwargs):
    subprocess.run(args, cwd=ROOT, encoding="utf-8", check=True, **kwargs)


def expected_sources(cfg):
    sources = [ROOT / value for value in cfg["build"]["cython_sources"]]
    for name in ["license_guard", "update_guard", "singleinstance_guard"]:
        sources.extend(
            path
            for path in sorted((ROOT / "commenlib" / name).glob("*.py"))
            if path.name not in {"__init__.py", "config.py", "example.py"}
        )
    return sources


def prepare():
    if WORK.exists():
        raise RuntimeError("存在上次构建工作目录，请先核对记录，不能覆盖或自动清空")
    cfg = yaml.safe_load((ROOT / "project.yaml").read_text(encoding="utf-8"))
    sources = expected_sources(cfg)
    for source in sources:
        if (
            list(source.parent.glob(source.stem + "*.pyd"))
            or source.with_suffix(".py.bak").exists()
        ):
            raise RuntimeError(f"源码旁已有未核对的编译产物：{source}")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    record_dir = ROOT / "outputs/build-records" / stamp
    record_dir.mkdir(parents=True)
    WORK.mkdir()
    node = Path(shutil.which("node.exe"))
    record = {
        "record_dir": str(record_dir),
        "version": str(cfg["app"]["version"]),
        "dist_dir": str(ROOT / "dist" / f"portable-{stamp}"),
        "node": str(node),
        "node_sha256": digest(node),
        "sources": {str(path.relative_to(ROOT)): digest(path) for path in sources},
        "artifacts": {},
        "status": "prepared",
    }
    save(record)
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"record_dir": str(record_dir)}), encoding="utf-8")
    front = ROOT / "frontend"
    build = front / ".next-portable"
    candidates = list((front / "src").rglob("*")) + [
        front / "next.config.ts",
        front / "package-lock.json",
    ]
    newest = max(path.stat().st_mtime for path in candidates if path.is_file())
    if (
        not (build / "BUILD_ID").exists()
        or (build / "BUILD_ID").stat().st_mtime < newest
    ):
        env = os.environ.copy()
        env.update(
            {
                "AIFACE_PORTABLE_BUILD": "1",
                "AIFACE_NEXT_DIST_DIR": ".next-portable",
                "AIFACE_BACKEND_ORIGIN": "http://127.0.0.1:18480",
            }
        )
        run([shutil.which("npm.cmd"), "--prefix", str(front), "run", "build"], env=env)
    if not (build / "standalone/server.js").is_file():
        raise RuntimeError("缺少 standalone 前端入口")
    if "127.0.0.1:18480" not in (build / "routes-manifest.json").read_text(
        encoding="utf-8"
    ):
        raise RuntimeError("便携前端 API 地址不匹配")
    print("构建目录：" + record["dist_dir"])


def verify_sources(record):
    for relative, expected in record["sources"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError(f"编译后源码发生变化，停止构建或清理：{relative}")


def module_name(relative):
    path = Path(relative).with_suffix("")
    parts = path.parts[1:] if path.parts[0] == "backend" else path.parts
    return ".".join(parts)


def compile_modules():
    record = load()
    verify_sources(record)
    record["status"] = "compiling"
    save(record)
    try:
        run(
            [
                sys.executable,
                "-X",
                "utf8",
                "scripts/portable-cython.py",
                "build_ext",
                "--build-temp",
                str(WORK / "temp"),
                "--build-lib",
                str(WORK / "lib"),
            ]
        )
    finally:
        for relative in record["sources"]:
            source = ROOT / relative
            name = module_name(relative)
            compiled = (
                WORK
                / "lib"
                / Path(*name.split(".")).with_suffix(
                    sysconfig.get_config_var("EXT_SUFFIX")
                )
            )
            artifact = source.with_name(
                source.stem + sysconfig.get_config_var("EXT_SUFFIX")
            )
            if compiled.is_file():
                if artifact.exists() and digest(artifact) != record["artifacts"].get(
                    str(artifact.relative_to(ROOT))
                ):
                    raise RuntimeError(f"源码旁存在未经核对的文件：{artifact}")
                shutil.copy2(compiled, artifact)
            if artifact.is_file():
                record["artifacts"][str(artifact.relative_to(ROOT))] = digest(artifact)
        save(record)
    if len(record["artifacts"]) != len(record["sources"]):
        raise RuntimeError("编译产物数量不匹配")
    record["status"] = "compiled"
    save(record)


def verify_artifacts(record):
    for relative, expected in record["artifacts"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise RuntimeError(f"产物来源或哈希不匹配：{path}")


def package():
    record = load()
    verify_sources(record)
    if record["status"] != "compiled" or len(record["artifacts"]) != len(
        record["sources"]
    ):
        raise RuntimeError("没有完整的本轮编译记录")
    verify_artifacts(record)
    if (Path(record["dist_dir"]) / "AIFACE").exists():
        raise RuntimeError("输出目录已存在，请先归档，不自动覆盖已有分发包")
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "portable.spec",
            "--noconfirm",
            "--workpath",
            str(WORK / "pyinstaller"),
            "--distpath",
            record["dist_dir"],
        ]
    )
    exe = Path(record["dist_dir"]) / "AIFACE/AIFACE.exe"
    record["exe_sha256"] = digest(exe)
    record["status"] = "packaged"
    save(record)


def copy_licenses(target):
    destination = target / "THIRD_PARTY_LICENSES"
    destination.mkdir()
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", destination / "Python-LICENSE.txt")
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        for file in dist.files or []:
            if any(
                part.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
                for part in file.parts
            ):
                source = Path(dist.locate_file(file))
                if source.is_file() and source.stat().st_size < 2_000_000:
                    folder = destination / "python" / name
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(
                        source,
                        folder / (str(file).replace("/", "_").replace("\\", "_")),
                    )
    for package_file in (target / "frontend/node_modules").rglob("package.json"):
        relative = package_file.parent.relative_to(target / "frontend")
        original = ROOT / "frontend" / relative
        for pattern in ["LICENSE*", "license*", "NOTICE*", "COPYING*"]:
            for source in original.glob(pattern):
                if source.is_file():
                    shutil.copy2(source, package_file.parent / source.name)
    shutil.copy2(
        ROOT / "scripts/portable-assets/face-parsing-LICENSE.txt",
        destination / "face-parsing-LICENSE.txt",
    )
    (destination / "face-parsing-source.txt").write_text(
        "https://github.com/yakhyo/face-parsing\n模型：weights/resnet18.onnx\n",
        encoding="utf-8",
    )
    for name in ["MobileSAM-LICENSE.txt", "samexporter-LICENSE.txt"]:
        shutil.copy2(ROOT / "scripts/portable-assets" / name, destination / name)
    (destination / "mobile-sam-source.txt").write_text(
        "模型项目：https://github.com/ChaoningZhang/MobileSAM\n"
        "ONNX 导出：https://github.com/vietanhdev/samexporter\n"
        "模型来源：https://huggingface.co/vietanhdev/segment-anything-onnx-models\n"
        "模型包：mobile_sam_20230629.zip\n"
        "SHA256：41aff2660b7531becfee21fb257c49933ddc892c554507bdb775bf504d443942\n",
        encoding="utf-8",
    )


def assemble():
    record = load()
    target = Path(record["dist_dir"]) / "AIFACE"
    standalone = ROOT / "frontend/.next-portable/standalone"
    shutil.copytree(
        standalone,
        target / "frontend",
        ignore=shutil.ignore_patterns(".env*", "*.map", "*.tsbuildinfo"),
    )
    shutil.copytree(ROOT / "frontend/public", target / "frontend/public")
    shutil.copytree(
        ROOT / "frontend/.next-portable/static",
        target / "frontend/.next-portable/static",
    )
    runtime = target / "runtime"
    runtime.mkdir()
    node = Path(record["node"])
    if digest(node) != record["node_sha256"]:
        raise RuntimeError("Node.js 文件在构建期间发生变化")
    shutil.copy2(node, runtime / "node.exe")
    shutil.copy2(node.parent / "LICENSE", runtime / "Node-LICENSE.txt")
    copy_licenses(target)
    (target / "README.txt").write_text(
        "AIFACE Windows 64 位便携版\n\n"
        "1. 将整个压缩包解压到有写入权限的目录，不要只复制 EXE，也不要在压缩包内运行。\n"
        "2. 双击 AIFACE.exe，浏览器自动打开工作台，无需安装 Python 或 Node.js。\n"
        "3. 输入软件卡密；进入模型设置填写自己的 API Key。生图需要联网并使用接口额度。\n"
        "4. 保留启动窗口。退出前等待生成结束，按 Ctrl+C 或关闭窗口退出。\n"
        "5. 数据在 storage，配置在 .env 和 codex-settings.json。升级前退出并备份它们。\n"
        "授权凭证存于当前 Windows 用户目录，不随压缩包提供；期限以授权服务器为准。\n"
        "本地区域及对象轮廓模型已自带，使用 CPU，不要求 CUDA。\n"
        "自动对象分析需要安装 Codex CLI 或包含 CLI 的桌面版，并登录自己的账号。\n"
        "模型设置页会检测 PATH 和常见安装目录，也可点击浏览选择 codex.exe 后保存。\n"
        "清空程序路径并保存可恢复自动检测；浏览选择仅支持本机网页。\n"
        "识别将把主照片发送给 Codex，按该账号的模型权限和额度运行，首次通常需数分钟。\n"
        "Codex 程序和登录凭证不随包分发；无需 Codex 的已有结果点选与轮廓修正可本地运行。\n"
        "本机端口：18480/18481。网页：http://127.0.0.1:18481\n"
        "遇到问题请保留 storage/logs 中本次日志。第三方许可见 THIRD_PARTY_LICENSES。\n",
        encoding="utf-8",
    )
    forbidden = [
        path
        for path in target.rglob("*")
        if path.is_file()
        and (
            path.name in {".env", "license.dat", "machine_id.dat", "codex-settings.json"}
            or path.suffix in {".sqlite3", ".db", ".bak"}
        )
    ]
    if forbidden:
        raise RuntimeError("分发目录中存在不应携带的配置或数据")
    record["status"] = "assembled"
    save(record)


def archive_intermediates():
    record = load()
    verify_sources(record)
    target = Path(record["dist_dir"]) / "AIFACE"
    if digest(target / "AIFACE.exe") != record["exe_sha256"]:
        raise RuntimeError("分发 EXE 哈希不一致")
    archive = Path(record["record_dir"]) / "compiled-modules"
    # 先核对全部路径及哈希，再移动；未知文件与原源码不动。
    verify_artifacts(record)
    for relative in record["artifacts"]:
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        (ROOT / relative).rename(destination)
    if WORK.resolve() != ROOT / ".commenlib-build" or WORK.is_symlink():
        raise RuntimeError("构建工作目录边界不匹配")
    WORK.rename(Path(record["record_dir"]) / "intermediates")
    verify_sources(record)
    record["status"] = "source_restored_and_intermediates_archived"
    save(record)
    print("源码已核对；本轮原地 PYD 和中间目录已归档，未删除未知文件。")


def main():
    parser = argparse.ArgumentParser(description="便携包构建步骤")
    parser.add_argument(
        "step", choices=["prepare", "compile", "package", "assemble", "archive"]
    )
    args = parser.parse_args()
    actions = {
        "prepare": prepare,
        "compile": compile_modules,
        "package": package,
        "assemble": assemble,
        "archive": archive_intermediates,
    }
    actions[args.step]()


if __name__ == "__main__":
    main()
