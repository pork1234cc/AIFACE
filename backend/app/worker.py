"""独立轮询进程：python -m app.worker；每个数据库仅允许一个 Worker。"""

import argparse
import hashlib
import io
import os
import sys
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import create_db_engine
from app.models.orders import Asset, GenerationBatch, GenerationTask, new_id, utc_now
from app.providers.apii import ApiiProvider, ProviderError
from app.schemas.deliveries import FinalsRequest
from app.services.assets import decode_upload
from app.services.deliveries import set_finals
from app.services.generation import aggregate, verify_input
from app.services.orders import BusinessError, write_session

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


class Worker:
    def __init__(self, settings: Settings, provider=None, poll_seconds: float = 5):
        self.settings = settings
        self.engine = create_db_engine(settings)
        self.provider = provider or ApiiProvider(settings)
        self.poll_seconds = poll_seconds
        self.lock = None

    def __enter__(self):
        self.lock = self.settings.database_path.with_suffix(".worker.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.lock.seek(0)
                # 文件锁由操作系统在进程退出时释放，不用删除锁文件。
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.close()
            raise RuntimeError("该数据库已有 Worker 正在运行") from exc
        try:
            self.recover()
        except Exception:
            self.close()
            raise
        return self

    def close(self):
        if self.lock:
            self.lock.close()
            self.lock = None
        self.provider.close()
        self.engine.dispose()

    def __exit__(self, *_):
        self.close()

    def recover(self):
        with write_session(self.engine) as session:
            tasks = session.scalars(
                select(GenerationTask).where(GenerationTask.status == "submitting")
            )
            for task in tasks:
                if task.provider_task_id:
                    task.status = "queued"
                else:
                    task.status = "submission_unknown"
                    task.error_code = "worker_interrupted"
                    task.error_message = "提交期间进程退出，受理结果不明，请人工核对"
                    task.failure_stage = "submit"
                aggregate(session, session.get(GenerationBatch, task.batch_id))

    def _next_poll(self, failures: int = 0) -> str:
        delay = max(self.poll_seconds, min(300, self.poll_seconds * 2 ** min(failures, 6)))
        return (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()

    def step(self) -> bool:
        if self.lock is None:
            raise RuntimeError("Worker 必须持有数据库进程锁")
        with write_session(self.engine) as session:
            task = session.scalar(
                select(GenerationTask)
                .where(
                    GenerationTask.status.in_({"pending", "queued", "running", "downloading"}),
                    or_(
                        GenerationTask.next_poll_at.is_(None),
                        GenerationTask.next_poll_at <= utc_now(),
                    ),
                )
                .order_by(GenerationTask.next_poll_at, GenerationTask.id)
                .limit(1)
            )
            if task is None:
                return False
            mode = task.status
            task.claimed_at = utc_now()
            if mode == "pending":
                task.status = "submitting"
            aggregate(session, session.get(GenerationBatch, task.batch_id))
        try:
            if mode == "pending":
                self._submit(task)
            elif mode == "downloading":
                self._download(task)
            else:
                self._query(task)
        except (ProviderError, BusinessError, OSError) as exc:
            self._failure(task.id, mode, exc)
        return True

    def _submit(self, task: GenerationTask):
        images = []
        with write_session(self.engine) as session:
            batch = session.get(GenerationBatch, task.batch_id)
            for snapshot in batch.input_snapshot_json:
                asset = session.get(Asset, snapshot["asset_id"])
                if asset is None or asset.order_id != batch.order_id:
                    raise BusinessError(422, "input_missing", "历史输入记录缺失")
                images.append(verify_input(self.settings.storage_path, asset, snapshot))
        # 在 HTTP 调用前落盘；崩溃恢复宁可要求核对，也不自动重发。
        with write_session(self.engine) as session:
            session.get(GenerationTask, task.id).submitted_at = utc_now()
        result = self.provider.submit(
            task.request_snapshot_json, images, task.provider_idempotency_key
        )
        with write_session(self.engine) as session:
            current = session.get(GenerationTask, task.id)
            current.provider_task_id, current.status = result["task_id"], "queued"
            current.next_poll_at = self._next_poll()
            aggregate(session, session.get(GenerationBatch, task.batch_id))

    def _query(self, task: GenerationTask):
        result = self.provider.query(task.provider_task_id)
        with write_session(self.engine) as session:
            current = session.get(GenerationTask, task.id)
            current.error_code = current.error_message = current.failure_stage = None
            current.poll_failures = 0
            current.status = result["status"]
            if result["status"] == "succeeded":
                current.result_metadata_json = {"url": result["url"]}
                current.status, current.next_poll_at = "downloading", None
            elif result["status"] == "failed":
                current.failure_stage, current.error_code = "remote", "remote_failed"
                current.error_message, current.finished_at = "供应商明确返回生成失败", utc_now()
            else:
                current.next_poll_at = self._next_poll()
            aggregate(session, session.get(GenerationBatch, task.batch_id))

    def _download(self, task: GenerationTask):
        data = self.provider.download(task.result_metadata_json["url"])
        decoded, extension, mime, width, height = decode_upload(io.BytesIO(data))
        with write_session(self.engine) as session:
            current = session.get(GenerationTask, task.id)
            batch = session.get(GenerationBatch, task.batch_id)
            relative = f"orders/{batch.order_id}/generated/{task.id}.{extension}"
            target = self.settings.storage_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(decoded).hexdigest()
            if target.exists():
                # 文件已写入而数据库尚未提交的恢复场景；绝不覆盖不同内容。
                with target.open("rb") as stored:
                    if hashlib.file_digest(stored, "sha256").hexdigest() != digest:
                        raise BusinessError(
                            409, "output_conflict", "既有结果文件内容不一致，请核对存储"
                        )
            else:
                temporary = target.with_suffix(f".{new_id()}.part")
                with temporary.open("xb") as output:
                    output.write(decoded)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.rename(target)
            asset = Asset(
                order_id=batch.order_id,
                kind="generated",
                input_role=None,
                is_active_input=False,
                generation_task_id=task.id,
                relative_path=relative,
                original_name=f"头像-{task.id[:8]}.{extension}",
                mime_type=mime,
                byte_size=len(decoded),
                width=width,
                height=height,
                sha256=digest,
                sort_index=task.slot_index,
            )
            session.add(asset)
            current.status, current.finished_at = "succeeded", utc_now()
            current.error_code = current.error_message = current.failure_stage = None
            # 敏感签名地址仅在待下载阶段留存。
            current.result_metadata_json = {
                "width": width,
                "height": height,
                "byte_size": len(data),
            }
            aggregate(session, batch)
            if batch.target_count == 1:
                # 图片、任务成功状态和当前交付图在同一事务提交；旧版本保留。
                set_finals(
                    session,
                    self.settings.storage_path,
                    batch.order_id,
                    FinalsRequest(asset_ids=[asset.id]),
                )

    def _failure(self, task_id: str, mode: str, error):
        with write_session(self.engine) as session:
            task = session.get(GenerationTask, task_id)
            task.error_code = getattr(error, "code", "storage_error")
            task.error_message = getattr(error, "message", "本地文件操作失败，请检查存储后恢复")
            if mode in {"queued", "running"}:
                if getattr(error, "remote_status", None) is not None:
                    task.result_metadata_json = {"unrecognized_status": error.remote_status}
                task.poll_failures += 1
                task.next_poll_at = self._next_poll(task.poll_failures)
                task.failure_stage = "protocol" if task.error_code != "query_failed" else "remote"
            else:
                task.status = (
                    "submission_unknown" if getattr(error, "uncertain", False) else "failed"
                )
                task.failure_stage = (
                    "submit"
                    if mode == "pending"
                    else ("persist" if isinstance(error, OSError) else "download")
                )
                task.finished_at = utc_now() if task.status == "failed" else None
            aggregate(session, session.get(GenerationBatch, task.batch_id))


def main():
    parser = argparse.ArgumentParser(description="AIFACE 独立生成 Worker")
    parser.add_argument("--once", action="store_true", help="执行一次可用任务后退出")
    args = parser.parse_args()
    try:
        with Worker(Settings()) as worker:
            print("生成 Worker 已启动；提交结果不明的任务不会自动重发。", flush=True)
            while True:
                worked = worker.step()
                if args.once:
                    break
                if not worked:
                    time.sleep(1)
    except KeyboardInterrupt:
        print("生成 Worker 已停止。", flush=True)
    except (RuntimeError, SQLAlchemyError, OSError) as exc:
        print(f"Worker 已停止（{type(exc).__name__}），请检查迁移、进程锁或存储。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
