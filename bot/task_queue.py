from __future__ import annotations

import asyncio
import logging
import os
import re
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

CLAIM_LEASE_SECONDS = settings.code_agent_stale_task_seconds
HEARTBEAT_SECONDS = 30.0
POLL_SECONDS = 1.0
RECOVERY_CHECK_SECONDS = 60.0
_ACTIVE_STATUSES = ("running", "planning", "branch_created", "committed", "pr_created", "changes_applied")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_tasks() -> int:
    """Requeue expired work so the persistent worker can reconcile it safely."""
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
            task.status = "queued"
            task.worker_id = None
            task.locked_at = None
            task.error = None
            recovered += 1
        if recovered:
            db.commit()
    if recovered:
        logger.warning("Requeued %s stale task(s) for crash recovery", recovered)
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


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _failure_reason(error: str | None, language: str) -> str:
    """Create a bounded user-facing diagnostic and redact common secrets."""
    raw = (error or "").strip()
    folded = raw.casefold()
    if not raw or raw == "no_changes":
        return {
            "fa": "عامل کد تغییر قابل‌اعمالی پیدا نکرد.",
            "hi": "एजेंट को लागू करने योग्य कोई बदलाव नहीं मिला।",
            "en": "The agent found no applicable code changes.",
        }.get(language, "The agent found no applicable code changes.")
    if any(term in folded for term in ("insufficient_quota", "quota exceeded", "rate limit", "429")):
        return {"fa": "سهمیه یا محدودیت نرخ مدل هوش مصنوعی تمام شده است.", "hi": "AI मॉडल की quota या rate limit पूरी हो गई है.", "en": "The AI model quota or rate limit was reached."}.get(language, "The AI model quota or rate limit was reached.")
    if any(term in folded for term in ("api key", "api_key", "unauthorized", "401")):
        return {"fa": "احراز هویت سرویس رد شد؛ کلید یا تنظیمات دسترسی را بررسی کن.", "hi": "सेवा ने प्रमाणीकरण अस्वीकार किया; API key या access settings जाँचें.", "en": "Service authentication failed; check the API key or access settings."}.get(language, "Service authentication failed; check the API key or access settings.")
    if any(term in folded for term in ("permission", "forbidden", "403", "resource not accessible")):
        return {"fa": "دسترسی لازم وجود ندارد؛ مجوزهای GitHub App و دسترسی مخزن را بررسی کن.", "hi": "ज़रूरी अनुमति नहीं है; GitHub App और repository permissions जाँचें.", "en": "Required permission is missing; check GitHub App and repository access."}.get(language, "Required permission is missing; check GitHub App and repository access.")
    if any(term in folded for term in ("repository not found", "repo not found", "404")):
        return {"fa": "مخزن یا منبع درخواستی پیدا نشد؛ نام مخزن و نصب GitHub App را بررسی کن.", "hi": "Repository या resource नहीं मिला; नाम और GitHub App installation जाँचें.", "en": "The repository or requested resource was not found; check its name and GitHub App installation."}.get(language, "The repository or requested resource was not found; check its name and GitHub App installation.")
    if "timeout" in folded or "timed out" in folded:
        return {"fa": "زمان انتظار درخواست تمام شد؛ سرویس مقصد یا اتصال شبکه را بررسی کن.", "hi": "अनुरोध का समय समाप्त हुआ; remote service या network जाँचें.", "en": "The request timed out; check the remote service or network connection."}.get(language, "The request timed out; check the remote service or network connection.")
    if "redis" in folded or "queue" in folded:
        return {"fa": "صف اجرا یا Redis خطا داده است؛ اتصال Redis و Worker را بررسی کن.", "hi": "Task queue या Redis में समस्या है; Redis और Worker जाँचें.", "en": "The task queue or Redis failed; check Redis and the worker."}.get(language, "The task queue or Redis failed; check Redis and the worker.")
    safe = re.sub(r"(?i)(token|secret|password|api[_ -]?key|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", raw)
    safe = re.sub(r"(?i)bearer\s+[^\s]+", "Bearer [redacted]", safe)
    safe = re.sub(r"(postgres(?:ql)?|redis)://[^\s]+", r"\1://[redacted]", safe)
    safe = safe[:500]
    prefix = {"fa": "خطای فنی: ", "hi": "तकनीकी त्रुटि: ", "en": "Technical error: "}.get(language, "Technical error: ")
    return prefix + safe


def _notify(task: Task, success: bool, result: dict | None = None, error: str | None = None) -> None:
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
        reason = _failure_reason(error, lang)
        if lang == "fa":
            text = f"اجرای کار ناموفق بود.\nعلت: {reason}\nجزئیات فنی کامل در لاگ سرور ثبت شده است."
        elif lang == "hi":
            text = f"कार्य विफल हुआ।\nकारण: {reason}\nपूरी तकनीकी जानकारी सर्वर लॉग में दर्ज है।"
        else:
            text = f"The task failed.\nReason: {reason}\nFull technical details are recorded in server logs."
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
        result = _run_async(
            execute_task,
            settings.gemini_api_key,
            settings.gemini_model,
            task.repository,
            task.request,
            task.installation_id,
            True,
            task.language,
            task.id,
        )
        if result.get("status") == "no_changes":
            fail_task(task.id, settings.gemini_model, "no_changes", refund=True)
            _notify(task, False, error="no_changes")
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
        _notify(task, False, error=str(exc))
    except Exception as exc:
        logger.exception("Unexpected task failure task_id=%s", task.id)
        fail_task(task.id, settings.gemini_model, str(exc)[:4000], refund=not side_effects_applied)
        _notify(task, False, error=str(exc))
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
