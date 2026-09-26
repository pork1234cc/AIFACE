# -*- coding: utf-8 -*-
"""编译步骤：执行编译命令并统计产物"""

import subprocess

from . import StepBase, StepRegistry
from ..utils import walk_project


@StepRegistry.register("compile")
class CompileStep(StepBase):
    """执行编译命令（如 Cython 编译）"""

    def execute(self, context) -> bool:
        command = context.resolve_template(self.config["command"])
        working_dir = self.config.get("working_dir")
        if working_dir:
            working_dir = context.resolve_template(working_dir)
        else:
            working_dir = str(context.root_dir)

        result = subprocess.run(command, cwd=working_dir, shell=True)
        if result.returncode != 0:
            return False

        # 统计产物数量
        output_ext = self.config.get("output_extensions", [])
        if output_ext:
            files = walk_project(context.root_dir, context.skip_dirs, output_ext)
            print(f"  编译完成，生成 {len(files)} 个产物文件")

        return True

    def dry_run(self, context):
        command = context.resolve_template(self.config["command"])
        print(f"  [dry-run] 将执行: {command}")
