# -*- coding: utf-8 -*-
"""工具函数：文件遍历、路径处理等"""

import os
import re
import sys
import stat
from pathlib import Path


PROTECTED_DIRS = {".git", ".venv", "venv", "venv_clean", "env", "node_modules"}


def is_protected_dir(path: Path, skip_dirs=()) -> bool:
    """禁止遍历虚拟环境、排除目录及链接/junction。"""
    names = {name.casefold() for name in PROTECTED_DIRS.union(skip_dirs)}
    if path.name.casefold() in names or (path / "pyvenv.cfg").is_file():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except FileNotFoundError:
        return False


def walk_project(root_dir: Path, skip_dirs: set, extensions: list[str]) -> list[Path]:
    """遍历项目目录，返回匹配扩展名的文件列表"""
    matched = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if not is_protected_dir(Path(root) / d, skip_dirs)]
        for f in files:
            if any(f.endswith(ext) for ext in extensions) and not (Path(root) / f).is_symlink():
                matched.append(Path(root) / f)
    return matched


def resolve_template(template: str, variables: dict) -> str:
    """替换模板字符串中的变量占位符

    支持:
      {var_name}   -> variables[var_name]
      {env:VAR}    -> os.environ[VAR]
    """
    def replacer(match):
        key = match.group(1)
        if key.startswith("env:"):
            env_name = key[4:]
            value = os.environ.get(env_name)
            if value is None:
                raise ValueError(f"环境变量 '{env_name}' 未设置")
            return value
        if key in variables:
            return str(variables[key])
        raise ValueError(f"未定义的变量 '{key}'")

    return re.sub(r"\{([^}]+)\}", replacer, template)


def safe_relative(path: Path, root: Path) -> bool:
    """检查 path 是否在 root 目录下（防止误删上级目录）"""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def get_default_variables(root_dir: Path) -> dict:
    """返回内置默认变量"""
    return {
        "python": sys.executable,
        "root_dir": str(root_dir),
    }
