"""显式指定命名空间包的扩展名称，避免 Cython 把宿主模块放到顶层。"""

import runpy
import sys
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

root = Path(__file__).resolve().parents[1]
helper = runpy.run_path(str(root / "scripts/portable-build.py"))
record = helper["load"]()
helper["verify_sources"](record)
extensions = [
    Extension(helper["module_name"](relative), [str(root / relative)])
    for relative in record["sources"]
]
setup(
    ext_modules=cythonize(
        extensions,
        build_dir=str(root / ".commenlib-build/cython"),
        force=True,
        compiler_directives={"language_level": "3"},
    ),
)
