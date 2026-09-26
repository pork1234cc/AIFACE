# -*- coding: utf-8 -*-
"""通用 Shell 步骤：执行任意 shell 命令"""

import subprocess

from . import StepBase, StepRegistry


@StepRegistry.register("shell")
class ShellStep(StepBase):
    """执行任意 shell 命令的通用步骤"""

    def execute(self, context) -> bool:
        command = context.resolve_template(self.config["command"])
        working_dir = self.config.get("working_dir")
        if working_dir:
            working_dir = context.resolve_template(working_dir)
        else:
            working_dir = str(context.root_dir)

        result = subprocess.run(command, cwd=working_dir, shell=True)
        return result.returncode == 0

    def dry_run(self, context):
        command = context.resolve_template(self.config["command"])
        print(f"  [dry-run] 将执行: {command}")
