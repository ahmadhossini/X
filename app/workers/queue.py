from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from core.config import settings


async def _enqueue(function: str, job_id: str, *args: object) -> str:
    """Enqueue using a pool owned by this call's event loop.

    The Telegram bot runs async work on short-lived event loops, while FastAPI
    has a long-lived loop. A module-global ARQ pool can therefore be reused
    from a different loop (or after its original loop has closed), causing
    errors such as "Event loop is closed". Keep the pool local and always
    close it before returning.
    """
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is required for the event queue")

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await pool.enqueue_job(function, *args, _job_id=job_id)
        if job is None:
            return job_id
        return job.job_id
    finally:
        await pool.close()


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
