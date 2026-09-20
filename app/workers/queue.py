from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from core.config import settings


_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is required for the event queue")
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def _enqueue(function: str, job_id: str, *args: object) -> str:
    pool = await get_pool()
    job = await pool.enqueue_job(function, *args, _job_id=job_id)
    if job is None:
        return job_id
    return job.job_id


async def enqueue_github_event(payload: dict) -> str:
    delivery_id = str(payload.get("_delivery_id") or "")
    if not delivery_id:
        raise RuntimeError("GitHub event delivery id is required")
    return await _enqueue("process_github_event", f"github:{delivery_id}", payload)


async def enqueue_coding_task(task_id: str) -> str:
    task_id = str(task_id or "")
    if not task_id:
        raise RuntimeError("Coding task id is required")
    return await _enqueue("process_coding_task", f"task:{task_id}", task_id)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
