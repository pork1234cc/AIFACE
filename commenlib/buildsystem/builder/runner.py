# -*- coding: utf-8 -*-
"""构建流水线编排"""

import sys
import time
from pathlib import Path

import yaml

from .steps import StepBase, StepRegistry
from .utils import get_default_variables, resolve_template, walk_project


class BuildContext:
    """在步骤间传递的共享上下文"""

    def __init__(self, config: dict):
        proj = config["project"]
        self.root_dir = Path(proj["root_dir"])
        self.skip_dirs = proj["skip_dirs"]

        # 合并变量：内置默认值 + 用户自定义
        self.variables = get_default_variables(self.root_dir)
        self.variables.update(config.get("variables", {}))
        # python 变量始终用当前解释器
        self.variables["python"] = sys.executable

    def resolve_template(self, template: str) -> str:
        return resolve_template(template, self.variables)

    def walk(self, extensions: list[str]) -> list[Path]:
        return walk_project(self.root_dir, self.skip_dirs, extensions)


class BuildRunner:
    """流水线编排器"""

    def __init__(self, config: dict):
        self.config = config
        self.context = BuildContext(config)
        self._steps = self._create_steps()

    def _create_steps(self) -> list[StepBase]:
        proj = self.config["project"]
        return [
            StepRegistry.create(step_cfg, proj)
            for step_cfg in self.config.get("steps", [])
        ]

    def list_steps(self):
        """列出所有步骤及其状态"""
        print(f"项目: {self.config['project']['name']}")
        print(f"根目录: {self.context.root_dir}")
        print(f"\n已配置 {len(self._steps)} 个步骤:")
        print("-" * 50)
        for i, step in enumerate(self._steps, 1):
            status = "启用" if step.enabled else "禁用"
            print(f"  {i}. [{status}] {step.name} ({step.config.get('type', 'shell')})")
            print(f"     {step.description}")
        print()

    def run(self, step_filter: str | None = None, dry_run: bool = False):
        """执行构建流水线

        Args:
            step_filter: 仅执行指定名称的步骤，None 表示全部
            dry_run: True 时仅打印不执行
        """
        if self.config["project"].get("require_host", False):
            self._validate_host()

        # 筛选步骤
        if step_filter:
            active = [s for s in self._steps if s.name == step_filter]
            if not active:
                print(f"错误: 未找到步骤 '{step_filter}'")
                sys.exit(1)
        else:
            active = [s for s in self._steps if s.enabled]

        if not active:
            print("没有可执行的步骤")
            return

        total = len(active)
        start = time.time()

        if dry_run:
            print("=" * 50)
            print("[dry-run 模式] 以下为将要执行的操作:")
            print("=" * 50)

        for i, step in enumerate(active, 1):
            step.log_banner(i, total)

            if dry_run:
                step.dry_run(self.context)
            else:
                success = step.execute(self.context)
                if not success:
                    print(f"[{i}/{total}] {step.name} 失败！")
                    if step.abort_on_failure:
                        print("中止构建。")
                        sys.exit(1)
                    else:
                        print("继续执行下一步...")
                else:
                    print(f"[{i}/{total}] {step.name} 完成\n")

        elapsed = time.time() - start
        print(f"总耗时: {elapsed:.1f} 秒")

    def _validate_host(self):
        """默认流水线必须在完整宿主布局中运行，先校验再执行任何步骤。"""
        root = self.context.root_dir.resolve()
        cfg_path = root / "project.yaml"
        if not cfg_path.is_file():
            raise FileNotFoundError(f"构建已停止：宿主配置不存在 {cfg_path}")
        with cfg_path.open(encoding="utf-8") as stream:
            cfg = yaml.safe_load(stream)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("build", {}), dict):
            raise ValueError("project.yaml 必须包含有效的构建配置")
        main_script = cfg.get("build", {}).get("main_script", "main.py")
        if not isinstance(main_script, str) or not main_script:
            raise ValueError("build.main_script 必须为非空路径")
        entry = (root / main_script).resolve()
        if not entry.is_relative_to(root) or not entry.is_file():
            raise ValueError(f"宿主入口不存在或超出项目目录: {entry}")
        expected = root / "commenlib/buildsystem/build_all.py"
        actual = Path(__file__).absolute().parents[1] / "build_all.py"
        if not expected.is_file() or expected.resolve() != actual.resolve():
            raise ValueError("默认构建要求当前组件位于宿主的 commenlib 目录")
