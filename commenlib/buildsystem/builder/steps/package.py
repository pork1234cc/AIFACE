# -*- coding: utf-8 -*-
"""打包步骤：执行打包命令（如 PyInstaller）"""

import subprocess
from pathlib import Path

from . import StepBase, StepRegistry
from ..utils import walk_project


@StepRegistry.register("package")
class PackageStep(StepBase):
    """执行打包命令"""

    def execute(self, context) -> bool:
        command = context.resolve_template(self.config["command"])
        working_dir = self.config.get("working_dir")
        if working_dir:
            working_dir = context.resolve_template(working_dir)
        else:
            working_dir = str(context.root_dir)

        # 临时隐藏有对应 .pyd 的 .py 文件，防止源码被打入包中
        hidden = self._hide_py_sources(context)
        try:
            result = subprocess.run(command, cwd=working_dir, shell=True)
        finally:
            self._restore_py_sources(hidden)

        return result.returncode == 0

    def _hide_py_sources(self, context) -> list[Path]:
        """将有对应 .pyd 的 .py 文件改名为 .py.bak，返回被隐藏的文件列表"""
        pyd_files = walk_project(context.root_dir, context.skip_dirs, [".pyd"])
        hidden = []
        for pyd in pyd_files:
            py = pyd.with_suffix(".py")
            if py.exists():
                py.rename(py.with_suffix(".py.bak"))
                hidden.append(py)
                print(f"  [隐藏源码] {py.relative_to(context.root_dir)}")
        return hidden

    def _restore_py_sources(self, hidden: list[Path]):
        """还原被隐藏的 .py 文件"""
        for py in hidden:
            bak = py.with_suffix(".py.bak")
            if bak.exists():
                bak.rename(py)

    def dry_run(self, context):
        command = context.resolve_template(self.config["command"])
        print(f"  [dry-run] 将执行: {command}")
