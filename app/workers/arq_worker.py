from __future__ import annotations

from arq.connections import RedisSettings
from arq.cron import cron

from app.workers.tasks import process_coding_task, process_github_event, reconcile_coding_tasks
from core.config import settings


class WorkerSettings:
    functions = [process_github_event, process_coding_task]
    cron_jobs = [
        cron(reconcile_coding_tasks, minute=None, second=0, run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.code_agent_workers
    job_timeout = settings.code_agent_job_timeout_seconds
    keep_result = 0
