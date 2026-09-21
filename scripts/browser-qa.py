"""隔离浏览器验收服务；仅使用本地模拟供应商，不发起真实供应商请求。"""

import argparse
import io
import json
import os
import sys
from pathlib import Path
from threading import Event, Thread

import uvicorn
from alembic import command
from alembic.config import Config
from app.api import generation
from app.config import PROJECT_ROOT, Settings
from app.db import create_db_engine
from app.main import create_app
from app.models.orders import GenerationBatch, GenerationTask
from app.providers.apii import ProviderError
from app.worker import Worker
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def picture(label):
    image = Image.new("RGB", (512, 512), "#fff8ec")
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 70, 392, 342), fill="#edc2a1", outline="#5a4a40", width=6)
    draw.ellipse((192, 170, 205, 186), fill="#40322c")
    draw.ellipse((307, 170, 320, 186), fill="#40322c")
    draw.arc((205, 215, 310, 280), 0, 180, fill="#40322c", width=5)
    draw.text((30, 420), label, fill="#40322c", font_size=24)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class LocalProvider:
    def __init__(self, settings):
        self.settings = settings
        self.engine = create_db_engine(settings)

    def close(self):
        self.engine.dispose()

    def submit(self, snapshot, images, key):
        if key.startswith("preview-"):
            record = {"key": key, "scenario": "QA_STYLE_PREVIEW", "input_count": len(images)}
            with (self.settings.storage_path / "simulated-submits.jsonl").open(
                "a", encoding="utf-8"
            ) as log:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
            return {"task_id": key, "status": "queued"}
        with Session(self.engine) as session:
            task = session.scalar(
                select(GenerationTask).where(
                    GenerationTask.provider_idempotency_key == key
                )
            )
            batch = session.get(GenerationBatch, task.batch_id)
            scenario = batch.params_snapshot_json.get("extra_requirement", "")
            record = {
                "key": key,
                "scenario": scenario,
                "slot": task.slot_index,
                "attempt": task.attempt_no,
                "input_count": len(images),
            }
        with (self.settings.storage_path / "simulated-submits.jsonl").open(
            "a", encoding="utf-8"
        ) as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
        if "QA_UNKNOWN" in scenario and task.slot_index == 0 and task.attempt_no == 1:
            raise ProviderError(
                "submission_unknown", "模拟提交中断，请核对", uncertain=True
            )
        return {"task_id": key, "status": "queued"}

    def query(self, remote_id):
        with Session(self.engine) as session:
            task = session.scalar(
                select(GenerationTask).where(
                    GenerationTask.provider_idempotency_key == remote_id
                )
            )
            batch = session.get(GenerationBatch, task.batch_id) if task else None
            failed = (
                batch
                and "QA_PARTIAL"
                in batch.params_snapshot_json.get("extra_requirement", "")
                and task.slot_index == 0
                and task.attempt_no == 1
            )
        return {
            "task_id": remote_id,
            "status": "failed" if failed else "succeeded",
            "url": f"https://example.invalid/{remote_id}",
            "model": "gpt-image-2.0-4k",
            "type": "edit",
        }

    def download(self, url):
        return picture("SIMULATED " + url.rsplit("/", 1)[-1][:12])


def main():
    parser = argparse.ArgumentParser(description="本地模拟浏览器验收")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to(PROJECT_ROOT / "storage") or not root.name.startswith(
        "qa-"
    ):
        raise ValueError("验收目录必须位于项目 storage/qa-* 下")
    root.mkdir(parents=True, exist_ok=True)
    os.environ["AIFACE_DATABASE_PATH"] = str(root / "database.sqlite3")
    os.environ["AIFACE_STORAGE_PATH"] = str(root)
    settings = Settings(_env_file=None, image_api=None)
    command.upgrade(Config(str(PROJECT_ROOT / "backend/alembic.ini")), "head")
    app = create_app(settings)
    manifest = root / "manifest.json"
    if not manifest.exists():
        orders = {}
        with TestClient(app) as client:
            for name, scenario in [
                ("单图成功", "QA_SUCCESS"),
                ("生成失败", "QA_PARTIAL"),
                ("关联远端", "QA_UNKNOWN_LINK"),
                ("确认未受理", "QA_UNKNOWN_CONFIRM"),
                ("风险重发", "QA_UNKNOWN_RISK"),
            ]:
                response = client.post(
                    "/api/orders", json={"customer_name": "模拟验收-" + name}
                )
                response.raise_for_status()
                order_id = response.json()["id"]
                for index, role in enumerate(
                    ["main", "material", "material", "material"]
                ):
                    response = client.post(
                        f"/api/orders/{order_id}/images",
                        data={"role": role},
                        files={
                            "file": (
                                f"模拟素材{index + 1}.png",
                                picture(role),
                                "image/png",
                            )
                        },
                    )
                    response.raise_for_status()
                    if index == 0:
                        main_id = response.json()["id"]
                response = client.patch(
                    f"/api/orders/{order_id}/params",
                    json={
                        "base_asset_id": main_id,
                        "extra_requirement": scenario,
                    },
                )
                response.raise_for_status()
                orders[name] = order_id
        manifest.write_text(
            json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    # 替换仅发生于此独立验收进程，生产入口不会导入本脚本。
    generation.ApiiProvider = LocalProvider
    stop = Event()

    def run_worker():
        with Worker(settings, LocalProvider(settings), 0.5) as worker:
            while not stop.is_set():
                if not worker.step():
                    stop.wait(0.2)

    thread = Thread(target=run_worker, daemon=True)
    thread.start()
    print("模拟验收服务已启动；真实供应商请求数为 0。", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    finally:
        stop.set()
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
