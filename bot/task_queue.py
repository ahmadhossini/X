from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from telebot import TeleBot

from billing.service import complete_task, fail_task, transition_task
from code_agent.agent import AgentError, execute_task, repair_task
from code_agent.github import GitHubRepo, GitHubRepoError
from code_agent.github_app import GitHubAppError
from core.config import settings
from database.models import Task
from database.session import SessionLocal

logger = logging.getLogger(__name__)

CLAIM_LEASE_SECONDS = 60 * 60
HEARTBEAT_SECONDS = 30.0
POLL_SECONDS = 1.0
RECOVERY_CHECK_SECONDS = 60.0
VALIDATION_POLL_SECONDS = 6.0
VALIDATION_TIMEOUT_SECONDS = 300.0
MAX_REPAIR_ATTEMPTS = 3
_ACTIVE_STATUSES = ("running", "planning", "branch_created", "validating", "retrying", "committed", "pr_created", "changes_applied")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def recover_stale_tasks() -> int:
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


def _validate_commit(repository: str, installation_id: int, commit_sha: str) -> dict:
    """Wait for the repository CI workflow attached to this exact commit."""
    async def _run() -> dict:
        repo = GitHubRepo(repository, installation_id)
        try:
            deadline = time.monotonic() + VALIDATION_TIMEOUT_SECONDS
            seen_run_ids: set[int] = set()
            while time.monotonic() < deadline:
                runs = await repo.workflow_runs_for_commit(commit_sha)
                relevant = []
                for run in runs:
                    run_id = run.get("id")
                    if not isinstance(run_id, int):
                        continue
                    seen_run_ids.add(run_id)
                    if run.get("event") in {"pull_request", "push"} or run.get("name") == "XAI Agent Validation":
                        relevant.append(run)
                if relevant:
                    latest = relevant[0]
                    status = str(latest.get("status") or "")
                    conclusion = str(latest.get("conclusion") or "")
                    if status == "completed":
                        if conclusion == "success":
                            return {"passed": True, "run_id": latest.get("id"), "name": latest.get("name")}
                        jobs = await repo.workflow_run_jobs(int(latest["id"]))
                        failures = [
                            f"{job.get('name', 'unknown')}: {job.get('conclusion', 'unknown')}"
                            for job in jobs
                            if job.get("conclusion") not in {None, "success", "skipped"}
                        ]
                        return {
                            "passed": False,
                            "run_id": latest.get("id"),
                            "name": latest.get("name"),
                            "failure": "; ".join(failures)[:12000] or f"Workflow conclusion: {conclusion or 'failure'}",
                        }
                await asyncio.sleep(VALIDATION_POLL_SECONDS)
            return {"passed": False, "failure": "Validation workflow did not complete within 5 minutes."}
        finally:
            await repo.aclose()
    return _run_async(_run)


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
            text = f"تغییرات با موفقیت اعتبارسنجی و آماده شد.\nمخزن: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        elif lang == "hi":
            text = f"Code changes सफलतापूर्वक validate होकर तैयार हैं.\nRepository: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        else:
            text = f"Code changes passed validation and are ready.\nRepository: {task.repository}\nBranch: {result.get('branch', '')}\nCommit: {str(result.get('commit', ''))[:12]}"
        if pr_url:
            text += f"\nPR: {pr_url}"
    else:
        if lang == "fa":
            text = "اجرای کار پس از ۳ تلاش اعتبارسنجی ناموفق بود. اعتبار رزرو‌شده برگردانده شد."
        elif lang == "hi":
            text = "3 validation attempts के बाद कार्य विफल हुआ। आरक्षित क्रेडिट वापस कर दिए गए।"
        else:
            text = "The task failed after 3 validation attempts. Reserved credits were refunded."
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
            _notify(task, False)
            return

        side_effects_applied = bool(result.get("commit") or result.get("branch") or result.get("pull_request"))
        branch = result.get("branch")
        commit_sha = result.get("commit")
        if not branch or not commit_sha:
            raise AgentError("Agent did not return a branch and commit")
        if not transition_task(task.id, "planning", "branch_created", branch=branch, commit_sha=commit_sha):
            raise AgentError("Task state changed while recording branch")

        validation = _validate_commit(task.repository, task.installation_id, commit_sha)
        if not transition_task(task.id, "branch_created", "validating"):
            raise AgentError("Task state changed while entering validation")

        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if validation.get("passed"):
                break
            failure = str(validation.get("failure") or "Validation failed without a detailed reason")
            if attempt >= MAX_REPAIR_ATTEMPTS:
                raise AgentError(f"Validation failed after {MAX_REPAIR_ATTEMPTS} attempts: {failure}")
            if not transition_task(task.id, "validating", "retrying", error=f"Validation attempt {attempt} failed: {failure}"):
                raise AgentError("Task state changed before validation retry")
            repair = _run_async(
                repair_task,
                settings.gemini_api_key,
                settings.gemini_model,
                task.repository,
                branch,
                task.request,
                failure,
                task.installation_id,
                task.language,
                task.id,
                attempt,
            )
            commit_sha = repair.get("commit")
            if not commit_sha:
                raise AgentError("Repair agent did not return a commit")
            result["commit"] = commit_sha
            result["changes"] = sorted(set(result.get("changes", [])) | set(repair.get("changes", [])))
            if not transition_task(task.id, "retrying", "validating", commit_sha=commit_sha, error=None):
                raise AgentError("Task state changed after validation retry")
            validation = _validate_commit(task.repository, task.installation_id, commit_sha)

        if not validation.get("passed"):
            raise AgentError("Validation did not pass")
        if not transition_task(task.id, "validating", "committed", commit_sha=commit_sha):
            raise AgentError("Task state changed while recording validated commit")
        pr = result.get("pull_request") or {}
        pr_number = pr.get("number")
        if pr_number:
            if not transition_task(task.id, "committed", "pr_created", pull_request_number=int(pr_number)):
                raise AgentError("Task state changed while recording pull request")
        complete_task(task.id, settings.gemini_model)
        _notify(task, True, result=result)
        logger.info("Task completed task_id=%s repository=%s", task.id, task.repository)
    except (AgentError, GitHubAppError, GitHubRepoError, RuntimeError) as exc:
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
