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

CLAIM_LEASE_SECONDS = 60 * 60
HEARTBEAT_SECONDS = 30.0
POLL_SECONDS = 1.0
RECOVERY_CHECK_SECONDS = 60.0
_ACTIVE_STATUSES = ("running", "planning", "branch_created", "committed", "pr_created", "changes_applied")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_tasks() -> int:
    """Stop expired active work conservatively; never blindly re-run side effects."""
    cutoff = _now() - timedelta(seconds=CLAIM_LEASE_SECONDS)
    recovered = 0
    with SessionLocal() as db:
        stale = list(
            db.scalars(
                select(Task)
                .where(Task.status.in_(_ACTIVE_STATUSES))
                .where(Task.locked_at.is_not(None), Task.locked_at < cutoff)
                .order_by(Task.created_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for task in stale:
            task.status = "failed"
            task.error = "Worker lease expired; task stopped to prevent duplicate repository side effects."
            task.worker_id = None
            task.completed_at = _now()
            recovered += 1
        if recovered:
            db.commit()
    if recovered:
        logger.error("Stopped %s stale task(s) after lease expiry; no automatic re-execution", recovered)
    return recovered


def claim_task(worker_id: str) -> Task | None:
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.status == "queued").order_by(Task.created_at.asc()).with_for_update(skip_locked=True))
        if not task:
            db.rollback()
            return None
        task.status = "running"
        task.worker_id = worker_id
        task.locked_at = _now()
        db.commit()
        return task


def _heartbeat_task(task_id: str, worker_id: str) -> bool:
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
    while not stop_event.wait(HEARTBEAT_SECONDS):
        try:
            if not _heartbeat_task(task_id, worker_id):
                logger.warning("Task lease lost task_id=%s worker_id=%s", task_id, worker_id)
                return
        except Exception:
            logger.exception("Task heartbeat failed task_id=%s", task_id)


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
            text = "اجرای کار متوقف یا ناموفق شد. برای جلوگیری از تغییر تکراری، اعتبار در صورت ایجاد تغییر مخزن به‌صورت خودکار بازگردانده نمی‌شود."
        elif lang == "hi":
            text = "कार्य रुक गया या विफल हुआ। दोबारा repository बदलाव से बचने के लिए, repository में बदलाव होने की स्थिति में क्रेडिट अपने-आप वापस नहीं किए जाते।"
        else:
            text = "The task stopped or failed. Credits are not automatically refunded when repository side effects may have occurred."
    try:
        bot.send_message(task.chat_id, text[:4000])
    except Exception:
        logger.exception("Telegram notification failed task_id=%s", task.id)


def _execute_claimed(task: Task, worker_id: str) -> None:
    if not transition_task(task.id, "running", "planning"):
        logger.warning("Task state changed before execution task_id=%s", task.id)
        return
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(target=_lease_heartbeat, args=(heartbeat_stop, task.id, worker_id), name=f"task-heartbeat-{task.id[:8]}", daemon=True)
    heartbeat.start()
    side_effects_applied = False
    try:
        result = asyncio.run(
            execute_task(
                settings.gemini_api_key,
                settings.gemini_model,
                task.repository,
                task.request,
                task.installation_id,
                True,
                task.language,
                task.id,
            )
        )
        if result.get("status") == "no_changes":
            fail_task(task.id, settings.gemini_model, "no_changes", refund=True)
            _notify(task, False)
            return

        side_effects_applied = bool(result.get("commit") or result.get("branch") or result.get("pull_request"))
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
            if not transition_task(task.id, "committed", "pr_created", pull_request_number=int(pr_number)):
                raise AgentError("Task state changed while recording pull request")
        complete_task(task.id, settings.gemini_model)
        _notify(task, True, result=result)
        logger.info("Task completed task_id=%s repository=%s", task.id, task.repository)
    except (AgentError, GitHubAppError, RuntimeError) as exc:
        logger.exception("Task failed task_id=%s repository=%s", task.id, task.repository)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000], refund=not side_effects_applied)
        _notify(task, False)
    except Exception as exc:
        logger.exception("Unexpected task failure task_id=%s", task.id)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000], refund=not side_effects_applied)
        _notify(task, False)
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2.0)


def worker_loop(stop_event) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    logger.info("Task worker started worker_id=%s", worker_id)
    recover_stale_tasks()
    next_recovery = _now().timestamp() + RECOVERY_CHECK_SECONDS
    while not stop_event.is_set():
        now = _now().timestamp()
        if now >= next_recovery:
            recover_stale_tasks()
            next_recovery = now + RECOVERY_CHECK_SECONDS
        task = claim_task(worker_id)
        if task is None:
            stop_event.wait(POLL_SECONDS)
            continue
        _execute_claimed(task, worker_id)
    logger.info("Task worker stopped worker_id=%s", worker_id)
