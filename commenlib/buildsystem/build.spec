# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件

宿主接入方式：commenlib 整目录拷贝到宿主项目根的 ``commenlib/`` 子目录，
``project.yaml`` 位于宿主项目根。本脚本会自动：
  1. 读取宿主根的 project.yaml
  2. 把 project.yaml 打入 _MEIPASS 根（commenlib/__init__.py 运行时读取）
  3. 自动收集 commenlib 包及其所有子模块作为 hidden imports，
     宿主无需在 project.yaml.build.hidden_imports 中声明 commenlib 相关项

运行：``python -m PyInstaller commenlib/buildsystem/build.spec --clean --noconfirm``
"""
import sys
from pathlib import Path
import yaml

from PyInstaller.utils.hooks import collect_submodules

# 路径计算（关键，区分两层目录）：
#   __file__         = <宿主根>/commenlib/buildsystem/build.spec
#   commenlib_dir    = <宿主根>/commenlib/
#   project_root     = <宿主根>/
# 用 absolute() 而非 resolve()：resolve 会展开符号链接/junction，
# 在 commenlib 通过 git submodule 或目录 junction 接入时会指向真实仓库位置而非宿主根
_THIS = Path(__file__).absolute()
_COMMENLIB_DIR = _THIS.parent.parent
_PROJECT_ROOT = _COMMENLIB_DIR.parent
_COMMENLIB_NAME = _COMMENLIB_DIR.name  # 默认 "commenlib"，宿主重命名时也自适应

# project.yaml 位于宿主项目根目录
_cfg_path = _PROJECT_ROOT / "project.yaml"
if not _cfg_path.exists():
    raise FileNotFoundError(
        f"找不到 project.yaml：{_cfg_path}\n"
        f"请将 {_COMMENLIB_NAME}/_template/project.yaml 复制到宿主项目根目录并填写配置。"
    )
with open(_cfg_path, encoding="utf-8") as _f:
    _cfg = yaml.safe_load(_f) or {}

_app = _cfg.get("app", {})
_build = _cfg.get("build", {})

APP_NAME    = _app.get("name", "App")
MAIN_SCRIPT = _build.get("main_script", "main.py")
ICON_FILE   = _build.get("icon_file") or None
CONSOLE     = bool(_build.get("console", False))

# datas：宿主声明的 + project.yaml（必须打入，commenlib/__init__.py 运行时要读）
DATAS = [tuple(d) for d in _build.get("extra_datas", [])]
DATAS.append((str(_cfg_path), "."))

# hidden_imports：宿主声明的 + commenlib 包及子模块（自动收集）
HIDDEN_IMPORTS = list(_build.get("hidden_imports", []))

# 把宿主根加入 pathex 确保 PyInstaller 能 import commenlib 进而收集其子模块
sys.path.insert(0, str(_PROJECT_ROOT))
try:
    _commenlib_submodules = collect_submodules(_COMMENLIB_NAME)
    HIDDEN_IMPORTS.extend(_commenlib_submodules)
    print(f"[build.spec] 自动收集 {_COMMENLIB_NAME} 子模块 "
          f"{len(_commenlib_submodules)} 个加入 hidden_imports")
finally:
    sys.path.pop(0)

# 去重（保持顺序）
_seen = set()
HIDDEN_IMPORTS = [x for x in HIDDEN_IMPORTS if not (x in _seen or _seen.add(x))]

# ------------------------------------------------------------------

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[str(_PROJECT_ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)
