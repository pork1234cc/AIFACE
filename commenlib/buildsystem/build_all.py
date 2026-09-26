# -*- coding: utf-8 -*-
"""
一键构建脚本：配置驱动的通用构建工具

用法:
    python build_all.py                  # 执行完整流程
    python build_all.py --clean-only     # 仅清除缓存
    python build_all.py --compile-only   # 仅编译PYD
    python build_all.py --package-only   # 仅打包EXE
    python build_all.py --list-steps     # 列出所有步骤
    python build_all.py --dry-run        # 预览将要执行的操作
    python build_all.py -c config.yaml   # 指定配置文件
"""

import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 确保 build/ 目录在 sys.path 中，以便导入 builder 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from builder.cli import build_cli  # noqa: E402

if __name__ == "__main__":
    build_cli()
