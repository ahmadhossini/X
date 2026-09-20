from __future__ import annotations

from arq.connections import RedisSettings

from app.workers.tasks import process_github_event
from core.config import settings


def _redis_settings() -> RedisSettings:
    if not settings.redis_url:
        raise RuntimeError(
            "REDIS_URL is required to start the ARQ worker. "
            "Configure Redis before deploying the worker."
        )
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    functions = [process_github_event]
    redis_settings = _redis_settings()
    max_jobs = settings.code_agent_workers
    job_timeout = 600
    keep_result = 0
