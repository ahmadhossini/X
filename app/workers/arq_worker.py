from __future__ import annotations

from arq.connections import RedisSettings

from app.workers.tasks import process_github_event
from core.config import settings


class WorkerSettings:
    functions = [process_github_event]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.code_agent_workers
    job_timeout = 600
    keep_result = 0
