"""隔离验收工具；默认只准备素材，--live 才调用真实供应商。"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.models.orders import GenerationTask
from app.services.generation import batch_data, get_batch
from app.services.orders import write_session
from app.worker import Worker
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def fixture(index: int) -> bytes:
    """绘制无真实人物信息的测试头像与配色参考。"""
    picture = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(picture)
    draw.ellipse((135, 90, 377, 345), fill="#f2ceb1", outline="#694e3c", width=5)
    draw.pieslice((132, 65, 380, 290), 180, 355, fill="#523c31")
    draw.ellipse((197, 197, 211, 211), fill="#40372e")
    draw.ellipse((299, 197, 313, 211), fill="#40372e")
    draw.arc((210, 230, 300, 282), 0, 180, fill="#935a46", width=5)
    draw.rounded_rectangle(
        (115, 340, 397, 510),
        radius=50,
        fill=["#6c8561", "#728caa", "#bd8f63", "#b59ab7"][index],
    )
    stream = io.BytesIO()
    picture.save(stream, format="PNG")
    return stream.getvalue()


def prepare(settings: Settings, report_path: Path):
    command.upgrade(Config(str(PROJECT_ROOT / "backend/alembic.ini")), "head")
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    with TestClient(create_app(settings)) as client:
        order = client.post(
            "/api/orders",
            json={
                "customer_name": "阶段3专用绘图测试",
                "note": "程序绘制素材，无真实人物信息",
            },
        ).json()
        inputs = []
        for index, role in enumerate(
            ["person_main", "person_aux", "person_aux", "reference"]
        ):
            response = client.post(
                f"/api/orders/{order['id']}/images",
                data={"role": role},
                files={
                    "file": (f"测试素材{index + 1}.png", fixture(index), "image/png")
                },
            )
            response.raise_for_status()
            inputs.append({"asset_id": response.json()["id"], "role": role})
        client.patch(
            f"/api/orders/{order['id']}/params",
            json={
                "hair_source_asset_id": inputs[0]["asset_id"],
                "clothes_mode": "reference",
                "clothes_source_asset_id": inputs[3]["asset_id"],
                "extra_requirement": "这是程序绘制的虚构测试人物，请生成一张独立头像。",
            },
        ).raise_for_status()
        response = client.post(
            f"/api/orders/{order['id']}/generate",
            json={"inputs": inputs},
            headers={"Idempotency-Key": "stage3-four-inputs"},
        )
        response.raise_for_status()
        report = {
            "order_id": order["id"],
            "batch_id": response.json()["batch_id"],
            "fixture": "程序绘图，四张输入",
            "live_started": False,
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report


def main():
    parser = argparse.ArgumentParser(description="阶段 3 隔离验收")
    parser.add_argument("--directory", default="storage/qa-stage3-20260920")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--seconds", type=int, default=45)
    args = parser.parse_args()
    root = (PROJECT_ROOT / args.directory).resolve()
    if (
        not root.is_relative_to(PROJECT_ROOT / "storage")
        or root == PROJECT_ROOT / "storage"
    ):
        raise ValueError("验收目录必须是 storage 内独立子目录")
    root.mkdir(parents=True, exist_ok=True)
    os.environ["AIFACE_DATABASE_PATH"] = str(root / "qa.sqlite3")
    os.environ["AIFACE_STORAGE_PATH"] = str(root)
    settings = Settings()
    report_path = root / "report.json"
    report = prepare(settings, report_path)
    if args.live:
        settings.require_image_api()
        report["live_started"] = True
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with Worker(settings) as worker:
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                worker.step()
                with write_session(worker.engine) as session:
                    detail = batch_data(session, get_batch(session, report["batch_id"]))
                if detail["status"] in {
                    "succeeded",
                    "partial_failed",
                    "failed",
                    "needs_attention",
                }:
                    break
                time.sleep(1)
            report["result"] = detail
            with write_session(worker.engine) as session:
                report["submission_count"] = len(
                    list(
                        session.scalars(
                            select(GenerationTask).where(
                                GenerationTask.submitted_at.is_not(None)
                            )
                        )
                    )
                )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
