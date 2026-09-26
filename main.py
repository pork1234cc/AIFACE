"""AIFACE 统一入口；冻结程序默认启动完整便携工作台。"""

import argparse
import multiprocessing
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="AIFACE 服务入口")
    parser.add_argument(
        "mode",
        choices=["api", "worker", "migrate", "desktop", "select-codex"],
        nargs="?",
        default="desktop" if getattr(sys, "frozen", False) else "api",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--smoke-test", action="store_true", help="验证便携启动后退出，不处理生成任务"
    )
    args = parser.parse_args(argv)
    if args.mode == "select-codex":
        from app.services.codex_runtime import picker_main

        return picker_main()
    if args.mode == "desktop":
        from app.portable import run_portable

        try:
            return run_portable(smoke_test=args.smoke_test)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"启动失败：{exc}", file=sys.stderr)
            if not args.smoke_test and sys.stdin and sys.stdin.isatty():
                input("按回车退出。")
            return 1
    elif args.mode == "api":
        import uvicorn
        from app.main import create_app

        uvicorn.run(create_app, factory=True, host="127.0.0.1", port=args.port)
    elif args.mode == "worker":
        from app.worker import main as worker_main

        return worker_main(["--api-port", str(args.port)])
    else:
        from alembic import command
        from alembic.config import Config
        from app.config import PROJECT_ROOT

        command.upgrade(Config(str(PROJECT_ROOT / "backend/alembic.ini")), "head")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
