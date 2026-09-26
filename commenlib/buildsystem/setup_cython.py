# -*- coding: utf-8 -*-
"""
Cython 编译配置文件

宿主接入方式：commenlib 整目录拷贝到宿主项目根的 ``commenlib/`` 子目录，
``project.yaml`` 位于宿主项目根。

宿主的 ``build.cython_sources`` 只填**宿主自身**的源码，
commenlib 内部的 license_guard / update_guard / singleinstance_guard
会被本脚本自动追加为编译目标，**无需**宿主声明。

运行：``python commenlib/buildsystem/setup_cython.py build_ext --inplace``
"""
from pathlib import Path
import sys
import yaml
from setuptools import setup
from Cython.Build import cythonize

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 路径计算（关键，区分两层目录）：
#   __file__         = <宿主根>/commenlib/buildsystem/setup_cython.py
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

# 宿主显式声明的源（相对宿主根）
HOST_SOURCES = list(_cfg.get("build", {}).get("cython_sources", []))

# commenlib 自身待编译的子模块目录
# 注：__init__.py / config.py / example.py 保持 .py 不编译——
#  - __init__.py：保留以维持包结构，且作为 PyInstaller 静态 import 解析入口
#  - config.py  ：含 dataclass，编译为 .pyd 后部分反射操作会出问题
#  - example.py ：纯示例代码，不参与运行时
_COMMENLIB_AUTO_DIRS = ["license_guard", "update_guard", "singleinstance_guard"]
_EXCLUDE_NAMES = {"__init__.py", "config.py", "example.py"}

_commenlib_sources: list[str] = []
for _sub in _COMMENLIB_AUTO_DIRS:
    _sub_dir = _COMMENLIB_DIR / _sub
    if not _sub_dir.exists():
        continue
    for _py in sorted(_sub_dir.glob("*.py")):
        if _py.name in _EXCLUDE_NAMES:
            continue
        _rel = _py.relative_to(_PROJECT_ROOT)
        _commenlib_sources.append(str(_rel).replace("\\", "/"))

# 合并去重（保持顺序：宿主优先）
_seen: set[str] = set()
SOURCE_FILES: list[str] = []
for _s in HOST_SOURCES + _commenlib_sources:
    if _s not in _seen:
        SOURCE_FILES.append(_s)
        _seen.add(_s)

if not SOURCE_FILES:
    print("[setup_cython] 无可编译源（宿主未声明且 commenlib 子模块缺失），跳过。")
else:
    print(f"[setup_cython] 共 {len(SOURCE_FILES)} 个源待编译："
          f"宿主 {len(HOST_SOURCES)} 个 + commenlib 自身 {len(_commenlib_sources)} 个")
    setup(
        ext_modules=cythonize(
            SOURCE_FILES,
            build_dir=str(_PROJECT_ROOT / ".commenlib-build" / "cython"),
            compiler_directives={"language_level": "3"},
        )
    )
