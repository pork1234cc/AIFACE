# -*- coding: utf-8 -*-
"""配置加载、校验与默认值合并"""

import re
from pathlib import Path

import yaml

from .steps import StepRegistry

# 导入所有步骤模块以触发注册
from .steps import clean, compile, package, shell  # noqa: F401

VALID_NAME_RE = re.compile(r"^[a-z0-9_-]+$")

DEFAULT_CONFIG = {
    "project": {
        "name": "project",
        "root_dir": ".",
        "skip_dirs": ["venv", ".git", "dist", "__pycache__"],
    },
    "steps": [],
    "variables": {},
}

# 需要 command 字段的步骤类型
COMMAND_TYPES = {"compile", "package", "shell"}
# 需要 clean_targets 字段的步骤类型
CLEAN_TYPES = {"clean", "post_clean"}


def load_config(config_path: str | None = None) -> dict:
    """加载 YAML 配置文件，合并默认值

    Args:
        config_path: 配置文件路径。为 None 时按优先级查找:
            1. 当前目录 build_config.yaml
            2. 脚本同目录 build_config.yaml
    """
    if config_path is None:
        candidates = [
            Path.cwd() / "build_config.yaml",
            Path(__file__).parent.parent / "build_config.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = str(candidate)
                break

    if config_path is None:
        print("未找到 build_config.yaml，使用默认配置")
        return _merge_defaults({}, None)

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = _merge_defaults(raw, config_file.parent)
    errors = validate_config(config)
    if errors:
        raise ValueError("配置校验失败:\n  " + "\n  ".join(errors))

    return config


def _merge_defaults(raw: dict, config_dir: Path | None) -> dict:
    """合并用户配置与默认值"""
    config = {}

    # project
    proj = {**DEFAULT_CONFIG["project"], **raw.get("project", {})}
    # 解析 root_dir 为绝对路径（相对于配置文件目录）
    root_dir = Path(proj["root_dir"])
    if not root_dir.is_absolute():
        base = config_dir if config_dir else Path.cwd()
        root_dir = (base / root_dir).resolve()
    proj["root_dir"] = str(root_dir)
    proj["skip_dirs"] = set(proj["skip_dirs"])
    config["project"] = proj

    # steps
    config["steps"] = raw.get("steps", DEFAULT_CONFIG["steps"])

    # variables
    config["variables"] = {
        **DEFAULT_CONFIG.get("variables", {}),
        **raw.get("variables", {}),
    }

    return config


def validate_config(config: dict) -> list[str]:
    """校验配置，返回错误列表（空列表表示通过）"""
    errors = []
    available_types = StepRegistry.available_types()

    steps = config.get("steps", [])
    if not steps:
        return errors  # 空步骤列表是允许的

    seen_names = set()
    for i, step in enumerate(steps):
        prefix = f"steps[{i}]"

        # name 必填
        name = step.get("name")
        if not name:
            errors.append(f"{prefix}: 缺少 'name' 字段")
            continue

        # name 格式校验
        if not VALID_NAME_RE.match(name):
            errors.append(
                f"{prefix}: name '{name}' 格式无效，仅允许 [a-z0-9_-]"
            )

        # name 唯一性
        if name in seen_names:
            errors.append(f"{prefix}: name '{name}' 重复")
        seen_names.add(name)

        # type 校验
        step_type = step.get("type", "shell")
        if step_type not in available_types:
            errors.append(
                f"{prefix}: 未知的 type '{step_type}'，"
                f"可用类型: {', '.join(available_types)}"
            )

        # command 字段检查
        if step_type in COMMAND_TYPES and "command" not in step:
            errors.append(f"{prefix}: type '{step_type}' 需要 'command' 字段")

        # clean_targets 字段检查
        if step_type in CLEAN_TYPES and "clean_targets" not in step:
            errors.append(
                f"{prefix}: type '{step_type}' 需要 'clean_targets' 字段"
            )

    return errors
