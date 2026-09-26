# -*- coding: utf-8 -*-
"""清理步骤：清除缓存和编译产物"""

import os
import shutil
from pathlib import Path

from . import StepBase, StepRegistry
from ..utils import is_protected_dir


def _validate_target(target: Path, root: Path, skip):
    """先验证完整路径，不能删除项目根、保护目录或链接。"""
    try:
        relative = target.resolve().relative_to(root.resolve())
        lexical = target.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError(f"清理目标不在项目目录内: {target}") from exc
    if not relative.parts or ".." in lexical.parts:
        raise ValueError(f"不允许清理项目根目录或上级路径: {target}")
    current = root
    for part in lexical.parts:
        current = current / part
        if is_protected_dir(current, skip):
            raise ValueError(f"不允许清理虚拟环境、保护目录或链接: {current}")
    # 显式目录的子树也不能包含虚拟环境或链接。
    for parent, dirs, _ in os.walk(target):
        for name in dirs:
            if is_protected_dir(Path(parent) / name, skip):
                raise ValueError(f"清理目标内含保护目录或链接: {Path(parent) / name}")


def _collect_targets(context, clean_targets: dict) -> list[Path]:
    """执行与预览共用完整清单；所有校验完成前不删除任何文件。"""
    if clean_targets.get("file_extensions"):
        raise ValueError("已禁止按扩展名递归清理，请将生成文件放入专用构建目录")
    root = context.root_dir
    skip = context.skip_dirs
    patterns = clean_targets.get("patterns", [])
    if any(pattern != "__pycache__" for pattern in patterns):
        raise ValueError("递归目录清理仅支持 __pycache__")
    targets = [root / name for name in clean_targets.get("dirs", [])]
    for target in targets:
        _validate_target(target, root, skip)
    if patterns:
        for parent, dirs, _ in os.walk(root):
            for name in list(dirs):
                path = Path(parent) / name
                if is_protected_dir(path, skip):
                    dirs.remove(name)
                elif name in patterns:
                    _validate_target(path, root, skip)
                    targets.append(path)
                    dirs.remove(name)
    return list(dict.fromkeys(targets))


def _do_clean(context, clean_targets: dict):
    """只清理通过边界校验的显式目录或 Python 缓存。"""
    for target in _collect_targets(context, clean_targets):
        if target.exists():
            shutil.rmtree(target)
            print(f"  已删除 {target}")


def _dry_run_clean(context, clean_targets: dict):
    """dry-run 模式下列出将要删除的内容"""
    for target in _collect_targets(context, clean_targets):
        if target.exists():
            print(f"  [dry-run] 将删除目录: {target}")


@StepRegistry.register("clean")
class CleanStep(StepBase):
    """清除缓存和编译产物"""

    def execute(self, context) -> bool:
        clean_targets = self.config.get("clean_targets", {})
        _do_clean(context, clean_targets)
        return True

    def dry_run(self, context):
        clean_targets = self.config.get("clean_targets", {})
        _dry_run_clean(context, clean_targets)


@StepRegistry.register("post_clean")
class PostCleanStep(StepBase):
    """构建后清理编译产物"""

    def execute(self, context) -> bool:
        clean_targets = self.config.get("clean_targets", {})
        _do_clean(context, clean_targets)
        return True

    def dry_run(self, context):
        clean_targets = self.config.get("clean_targets", {})
        _dry_run_clean(context, clean_targets)
