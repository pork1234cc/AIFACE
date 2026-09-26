# -*- mode: python ; coding: utf-8 -*-
"""宿主便携文件夹构建；前端与 Node 在打包后按白名单组装。"""

from pathlib import Path

import yaml
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

root = Path(SPECPATH)
cfg = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
datas = []
for source, destination in cfg["build"]["extra_datas"]:
    path = root / source
    if path.is_dir():
        for item in path.rglob("*"):
            if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
                datas.append((str(item), str(Path(destination) / item.relative_to(path).parent)))
    else:
        datas.append((str(path), destination))
datas.append((str(root / "project.yaml"), "."))
hidden = list(cfg["build"]["hidden_imports"])
for package in ["app", "commenlib.license_guard", "commenlib.update_guard"]:
    hidden.extend(collect_submodules(package))
hidden.extend(["requests", "yaml", "platform", "uuid", "tkinter", "tkinter.messagebox"])
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root), str(root / "backend")],
    binaries=collect_dynamic_libs("onnxruntime"),
    datas=datas,
    hiddenimports=sorted(set(hidden)),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["pytest", "Cython", "PyInstaller", "commenlib.buildsystem"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="AIFACE", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AIFACE")
