from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from billing.service import complete_task, fail_task, transition_task
from code_agent.agent import AgentError, execute_task
from code_agent.github_app import GitHubAppError
from core.config import settings
from database.models import Task
from database.session import SessionLocal

logger = logging.getLogger(__name__)

CLAIM_LEASE_SECONDS = 15 * 60
POLL_SECONDS = 1.0
_ACTIVE_STATUSES = ("running", "planning", "branch_created", "committed", "pr_created")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_tasks() -> int:
    cutoff = _now() - timedelta(seconds=CLAIM_LEASE_SECONDS)
    with SessionLocal() as db:
        result = db.execute(
            update(Task)
            .where(Task.status.in_(_ACTIVE_STATUSES))
            .where(Task.locked_at.is_not(None), Task.locked_at < cutoff)
            .values(
                status="queued",
                worker_id=None,
                locked_at=None,
                error="Worker lease expired; task requeued",
            )
        )
        db.commit()
        return result.rowcount or 0


def claim_task(worker_id: str) -> Task | None:
    with SessionLocal() as db:
        task = db.scalar(
            select(Task)
            .where(Task.status == "queued")
            .order_by(Task.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        if not task:
            db.rollback()
            return None
        task.status = "running"
        task.worker_id = worker_id
        task.locked_at = _now()
        db.commit()
        return task


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _execute_claimed(task: Task) -> None:
    if not transition_task(task.id, "running", "planning"):
        logger.warning("Task state changed before execution task_id=%s", task.id)
        return

    try:
        result = _run_async(
            execute_task,
            settings.gemini_api_key,
            settings.gemini_model,
            task.repository,
            task.request,
            task.installation_id,
            True,
            None,
        )

        if result.get("status") == "no_changes":
            fail_task(task.id, settings.gemini_model, "no_changes")
            return

        branch = result.get("branch")
        if not branch:
            raise AgentError("Agent did not return a branch")
        if not transition_task(task.id, "planning", "branch_created", branch=branch):
            raise AgentError("Task state changed while creating branch")

        commit_sha = result.get("commit")
        if not commit_sha:
            raise AgentError("Agent did not return a commit")
        if not transition_task(task.id, "branch_created", "committed", commit_sha=commit_sha):
            raise AgentError("Task state changed while recording commit")

        pr = result.get("pull_request") or {}
        pr_number = pr.get("number")
        if pr_number:
            if not transition_task(
                task.id,
                "committed",
                "pr_created",
                pull_request_number=int(pr_number),
            ):
                raise AgentError("Task state changed while recording pull request")

        complete_task(task.id, settings.gemini_model)
        logger.info("Task completed task_id=%s repository=%s", task.id, task.repository)
    except (AgentError, GitHubAppError, RuntimeError) as exc:
        logger.exception("Task failed task_id=%s repository=%s", task.id, task.repository)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000])
    except Exception as exc:
        logger.exception("Unexpected task failure task_id=%s", task.id)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000])


def worker_loop(stop_event) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    logger.info("Task worker started worker_id=%s", worker_id)
    recover_stale_tasks()
    while not stop_event.is_set():
        task = claim_task(worker_id)
        if task is None:
            stop_event.wait(POLL_SECONDS)
            continue
        _execute_claimed(task)
    logger.info("Task worker stopped worker_id=%s", worker_id)
