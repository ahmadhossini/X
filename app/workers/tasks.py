from __future__ import annotations

import asyncio
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.workers.github_events import route_github_event
from app.workers.queue import enqueue_coding_task
from bot.task_queue import _execute_claimed
from database.models import Task, WebhookEvent
from database.session import SessionLocal

logger = logging.getLogger(__name__)
STALE_TASK_LEASE = timedelta(hours=1)
ACTIVE_TASK_STATUSES = ("running", "planning", "branch_created", "committed", "pr_created", "changes_applied")


def _claim_coding_task(task_id: str, worker_id: str) -> Task | None:
    with SessionLocal() as db:
        task = db.scalar(
            select(Task)
            .where(Task.id == task_id)
            .where(Task.status == "queued")
            .with_for_update()
        )
        if not task:
            return None
        task.status = "running"
        task.worker_id = worker_id
        task.locked_at = datetime.now(timezone.utc)
        db.commit()
        return task


async def process_coding_task(ctx: dict[str, Any], task_id: str) -> None:
    """Process exactly one persisted coding task through the shared agent engine."""
    task_id = str(task_id or "")
    if not task_id:
        raise ValueError("Coding task id is required")
    worker_id = f"arq:{socket.gethostname()}:{task_id[:12]}"
    task = _claim_coding_task(task_id, worker_id)
    if task is None:
        logger.info("Coding task already claimed or completed task_id=%s", task_id)
        return
    await asyncio.to_thread(_execute_claimed, task, worker_id)


async def reconcile_coding_tasks(ctx: dict[str, Any]) -> None:
    """Repair queued jobs lost during a deploy and requeue stale worker leases."""
    cutoff = datetime.now(timezone.utc) - STALE_TASK_LEASE
    stale_ids: list[str] = []
    queued_ids: list[str] = []
    with SessionLocal() as db:
        stale = list(
            db.scalars(
                select(Task)
                .where(Task.status.in_(ACTIVE_TASK_STATUSES))
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
            stale_ids.append(task.id)

        queued_ids = list(
            db.scalars(
                select(Task.id)
                .where(Task.status == "queued")
                .order_by(Task.created_at.asc())
                .limit(100)
            )
        )
        if stale_ids:
            db.commit()

    for task_id in queued_ids:
        try:
            await enqueue_coding_task(task_id)
        except Exception:
            logger.exception("Failed to reconcile queued coding task task_id=%s", task_id)

    if stale_ids:
        logger.warning("Requeued stale coding tasks count=%s", len(stale_ids))


async def process_github_event(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """Route a GitHub event and mark it processed only after successful handling."""
    delivery_id = str(payload.get("_delivery_id") or "")
    event_type = str(payload.get("_event_type") or "unknown")
    if not delivery_id:
        raise ValueError("GitHub event delivery id is required")

    with SessionLocal() as db:
        event = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first()
        if event is None:
            raise ValueError(f"GitHub webhook record not found: {delivery_id}")
        if event.processed:
            logger.info("GitHub event already processed delivery_id=%s", delivery_id)
            return

    try:
        await route_github_event({**payload, "_event_type": event_type})
    except Exception:
        logger.exception(
            "GitHub event handler failed delivery_id=%s event_type=%s",
            delivery_id,
            event_type,
        )
        raise

    with SessionLocal() as db:
        event = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first()
        if event is None:
            raise ValueError(f"GitHub webhook record disappeared: {delivery_id}")
        if not event.processed:
            event.processed = True
            db.commit()
    logger.info(
        "GitHub event processed delivery_id=%s event_type=%s",
        delivery_id,
        event_type,
    )
