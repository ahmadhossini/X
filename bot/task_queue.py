from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from telebot import TeleBot

from billing.service import complete_task, fail_task, transition_task
from code_agent.agent import AgentError, execute_task
from code_agent.github_app import GitHubAppError
from core.config import settings
from database.models import Task
from database.session import SessionLocal

logger = logging.getLogger(__name__)

# Do not automatically retry a task after it may have performed GitHub writes.
# Without idempotent branch/commit/PR reconciliation, a retry can create duplicate changes.
CLAIM_LEASE_SECONDS = 60 * 60
HEARTBEAT_SECONDS = 30.0
POLL_SECONDS = 1.0
_ACTIVE_STATUSES = ("running", "planning", "branch_created", "committed", "pr_created")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_tasks() -> int:
    """Fail expired leases instead of requeueing potentially side-effected work."""
    cutoff = _now() - timedelta(seconds=CLAIM_LEASE_SECONDS)
    with SessionLocal() as db:
        stale_ids = list(
            db.scalars(
                select(Task.id)
                .where(Task.status.in_(_ACTIVE_STATUSES))
                .where(Task.locked_at.is_not(None), Task.locked_at < cutoff)
                .limit(100)
            )
        )

    recovered = 0
    for task_id in stale_ids:
        fail_task(task_id, settings.gemini_model, "worker_lease_expired")
        recovered += 1
    return recovered


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


def _heartbeat_task(task_id: str, worker_id: str) -> bool:
    """Refresh a worker lease only while this worker still owns the active task."""
    with SessionLocal() as db:
        result = db.execute(
            update(Task)
            .where(Task.id == task_id)
            .where(Task.worker_id == worker_id)
            .where(Task.status.in_(_ACTIVE_STATUSES))
            .values(locked_at=_now())
        )
        db.commit()
        return result.rowcount == 1


def _lease_heartbeat(stop_event: threading.Event, task_id: str, worker_id: str) -> None:
    """Keep long-running Gemini/GitHub work from being mistaken for a dead worker."""
    while not stop_event.wait(HEARTBEAT_SECONDS):
        try:
            if not _heartbeat_task(task_id, worker_id):
                logger.warning("Task lease lost task_id=%s worker_id=%s", task_id, worker_id)
                return
        except Exception:
            logger.exception("Task heartbeat failed task_id=%s worker_id=%s", task_id, worker_id)


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _notify(task: Task, success: bool, result: dict | None = None) -> None:
    if not task.chat_id:
        return
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        logger.error("BOT_TOKEN is missing; cannot notify task_id=%s", task.id)
        return
    bot = TeleBot(token, parse_mode=None)
    lang = task.language if task.language in {"en", "hi", "fa"} else "en"
    result = result or {}
    if success:
        pr = result.get("pull_request") or {}
        pr_url = pr.get("url") or ""
        if lang == "fa":
            text = f"تغییرات کد آماده شد.\nمخزن: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        elif lang == "hi":
            text = f"Code changes तैयार हैं.\nRepository: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        else:
            text = f"Code changes are ready.\nRepository: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        if pr_url:
            text += f"\nPR: {pr_url}"
    else:
        if lang == "fa":
            text = "اجرای کار ناموفق بود و اعتبار رزرو‌شده برگردانده شد."
        elif lang == "hi":
            text = "कार्य विफल हुआ और आरक्षित क्रेडिट वापस कर दिए गए।"
        else:
            text = "The task failed and the reserved credits were refunded."
    try:
        bot.send_message(task.chat_id, text[:4000])
    except Exception:
        logger.exception("Telegram notification failed task_id=%s", task.id)


def _execute_claimed(task: Task, worker_id: str) -> None:
    if not transition_task(task.id, "running", "planning"):
        logger.warning("Task state changed before execution task_id=%s", task.id)
        return

    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_lease_heartbeat,
        args=(heartbeat_stop, task.id, worker_id),
        name=f"task-heartbeat-{task.id[:8]}",
        daemon=True,
    )
    heartbeat.start()

    try:
        result = _run_async(
            execute_task,
            settings.gemini_api_key,
            settings.gemini_model,
            task.repository,
            task.request,
            task.installation_id,
            True,
            task.language,
        )

        if result.get("status") == "no_changes":
            fail_task(task.id, settings.gemini_model, "no_changes")
            _notify(task, False)
            return

        branch = result.get("branch")
        if not branch:
            raise AgentError("Agent did not return a branch")
        if not transition_task(task.id, "planning", "branch_created", branch=branch):
            raise AgentError("Task state changed while recording branch")

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
        _notify(task, True, result=result)
        logger.info("Task completed task_id=%s repository=%s", task.id, task.repository)
    except (AgentError, GitHubAppError, RuntimeError) as exc:
        logger.exception("Task failed task_id=%s repository=%s", task.id, task.repository)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000])
        _notify(task, False)
    except Exception as exc:
        logger.exception("Unexpected task failure task_id=%s", task.id)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000])
        _notify(task, False)
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2.0)


def worker_loop(stop_event) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    logger.info("Task worker started worker_id=%s", worker_id)
    recovered = recover_stale_tasks()
    if recovered:
        logger.warning("Marked %s stale task(s) failed to avoid duplicate GitHub writes", recovered)
    while not stop_event.is_set():
        task = claim_task(worker_id)
        if task is None:
            stop_event.wait(POLL_SECONDS)
            continue
        _execute_claimed(task, worker_id)
    logger.info("Task worker stopped worker_id=%s", worker_id)
