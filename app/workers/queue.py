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


async def enqueue_github_event(payload: dict) -> str:
    pool = await get_pool()
    delivery_id = str(payload.get("_delivery_id") or "")
    job = await pool.enqueue_job(
        "process_github_event",
        payload,
        _job_id=f"github:{delivery_id}" if delivery_id else None,
    )
    if job is None:
        if delivery_id:
            return f"github:{delivery_id}"
        raise RuntimeError("GitHub event job was rejected")
    return job.job_id


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
