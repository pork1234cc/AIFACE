# -*- coding: utf-8 -*-
"""步骤基类与注册机制"""

from abc import ABC, abstractmethod


class StepBase(ABC):
    """所有构建步骤的抽象基类"""

    def __init__(self, config: dict, project_config: dict):
        self.name = config["name"]
        self.enabled = config.get("enabled", True)
        self.abort_on_failure = config.get("abort_on_failure", True)
        self.description = config.get("description", self.name)
        self.config = config
        self.project_config = project_config

    @abstractmethod
    def execute(self, context) -> bool:
        """执行步骤，返回 True=成功 / False=失败"""

    def dry_run(self, context):
        """dry-run 模式下打印将要执行的内容"""
        print(f"  [dry-run] 步骤 '{self.name}': {self.description}")

    def log_banner(self, index: int, total: int):
        print("=" * 50)
        print(f"[{index}/{total}] {self.description}")
        print("=" * 50)


class StepRegistry:
    """type 名到 StepBase 子类的映射注册表"""

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, type_name: str):
        def decorator(step_cls):
            cls._registry[type_name] = step_cls
            return step_cls
        return decorator

    @classmethod
    def create(cls, step_config: dict, project_config: dict) -> StepBase:
        type_name = step_config.get("type", "shell")
        if type_name not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"未知的步骤类型 '{type_name}'，可用类型: {available}"
            )
        return cls._registry[type_name](step_config, project_config)

    @classmethod
    def available_types(cls) -> list[str]:
        return sorted(cls._registry.keys())
