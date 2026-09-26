# -*- coding: utf-8 -*-
"""CLI 入口：两阶段 argparse 动态生成步骤参数"""

import argparse
import sys

from .config import load_config
from .runner import BuildRunner


def build_cli(argv=None):
    """构建工具 CLI 入口"""
    # 阶段1: 预解析获取 --config 路径
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", "-c", default=None)
    pre_args, _ = pre_parser.parse_known_args(argv)

    # 加载配置
    try:
        config = load_config(pre_args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 阶段2: 完整解析（含动态步骤参数）
    parser = argparse.ArgumentParser(
        description="通用构建工具：配置驱动的多步骤构建流程"
    )
    parser.add_argument("--config", "-c", default=None,
                        help="指定配置文件路径 (默认: build_config.yaml)")
    parser.add_argument("--list-steps", action="store_true",
                        help="列出所有已配置的步骤及其状态")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将要执行的步骤，不实际执行")

    # 动态生成 --{name}-only 参数
    steps = config.get("steps", [])
    if steps:
        step_group = parser.add_mutually_exclusive_group()
        for step_cfg in steps:
            name = step_cfg["name"]
            desc = step_cfg.get("description", name)
            step_group.add_argument(
                f"--{name}-only",
                action="store_true",
                help=f"仅执行: {desc}",
            )

    args = parser.parse_args(argv)

    runner = BuildRunner(config)

    # 处理 --list-steps
    if args.list_steps:
        runner.list_steps()
        return

    # 判断是否指定了单步执行
    selected_step = None
    for step_cfg in steps:
        attr_name = step_cfg["name"].replace("-", "_") + "_only"
        if getattr(args, attr_name, False):
            selected_step = step_cfg["name"]
            break

    try:
        runner.run(step_filter=selected_step, dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
