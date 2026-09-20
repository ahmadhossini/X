from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.billing.plans import PLANS
from core.config import settings
from database.models import GitHubInstallation, Subscription, Task, UsageRecord, User
from database.session import SessionLocal

ACTIVE_TASK_STATUSES = (
    "queued",
    "running",
    "planning",
    "branch_created",
    "committed",
    "pr_created",
    "changes_applied",
)


class BillingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreditReservation:
    task_id: str
    credits: int
    remaining: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _monthly_credits(plan_key: str) -> int:
    if plan_key == "free":
        return settings.free_monthly_credits
    if plan_key == "pro":
        return settings.pro_monthly_credits
    if plan_key in {"team", "pro_plus"}:
        return settings.team_monthly_credits
    return PLANS["free"].monthly_credits


def _reset_credit_state(db, user: User, now: datetime) -> None:
    if user.credits_reset_at is not None and user.credits_reset_at > now:
        return

    if user.plan == "free":
        user.credits = _monthly_credits("free")
        user.credits_reset_at = now + timedelta(days=30)
        return

    subscription = db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .with_for_update()
    )
    if subscription is None:
        # Backward-compatible fallback for older paid users created before the
        # subscription row existed. Their credits still reset monthly.
        user.credits = _monthly_credits(user.plan)
        user.credits_reset_at = now + timedelta(days=30)
        return

    if subscription.status == "active" and subscription.expires_at and subscription.expires_at > now:
        user.credits = _monthly_credits(user.plan)
        user.credits_reset_at = min(
            subscription.expires_at,
            now + timedelta(days=30),
        )
        return

    subscription.status = "expired"
    subscription.plan = "free"
    subscription.expires_at = now
    user.plan = "free"
    user.credits = 0
    user.credits_reset_at = now


def ensure_user_credit_state(telegram_id: int) -> tuple[int, str]:
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(User.telegram_id == telegram_id)
            .with_for_update()
        )
        if not user:
            raise BillingError("User not found")
        _reset_credit_state(db, user, _now())
        db.commit()
        return user.credits, user.plan


def estimate_task_credits(request: str) -> int:
    """Estimate conservatively because /task can modify repository files."""
    text = request.lower()
    heavy_terms = (
        "bug", "debug", "error", "exception", "failing", "broken", "crash",
        "باگ", "خطا", "ارور", "خرابی", "رفع مشکل", "دیباگ",
    )
    if any(term in text for term in heavy_terms):
        return 10
    return 5


def reserve_task_credits(
    telegram_id: int,
    repository: str,
    request: str,
    credits: int,
    *,
    installation_id: int | None = None,
    model: str = "",
    chat_id: int | None = None,
    language: str = "en",
) -> CreditReservation:
    if credits <= 0:
        raise BillingError("Invalid task reservation")

    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(User.telegram_id == telegram_id)
            .with_for_update()
        )
        if not user:
            raise BillingError("User not found")

        active_task = db.scalar(
            select(Task.id)
            .where(
                Task.user_id == user.id,
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
            .limit(1)
        )
        if active_task:
            raise BillingError("Active task already exists")

        installation = None
        if installation_id:
            installation = db.scalar(
                select(GitHubInstallation).where(
                    GitHubInstallation.installation_id == installation_id,
                    GitHubInstallation.user_id == user.id,
                    GitHubInstallation.active.is_(True),
                )
            )
        else:
            installation = db.scalar(
                select(GitHubInstallation)
                .where(
                    GitHubInstallation.user_id == user.id,
                    GitHubInstallation.active.is_(True),
                )
                .order_by(GitHubInstallation.updated_at.desc())
            )
        if not installation:
            raise BillingError("GitHub not connected")

        now = _now()
        _reset_credit_state(db, user, now)
        if user.credits < credits:
            db.rollback()
            raise BillingError("Insufficient credits")

        user.credits -= credits
        task_id = uuid4().hex
        task = Task(
            id=task_id,
            user_id=user.id,
            installation_id=installation.installation_id,
            repository=repository,
            request=request[:4000],
            model=model[:255],
            status="queued",
            chat_id=chat_id,
            language=language[:8] or "en",
        )
        usage = UsageRecord(
            task_id=task_id,
            user_id=user.id,
            repository=repository,
            request=request[:4000],
            model=model[:255],
            credits_reserved=credits,
            credits_used=0,
            status="reserved",
        )
        db.add(task)
        db.add(usage)
        db.commit()
        return CreditReservation(
            task_id=task_id,
            credits=credits,
            remaining=user.credits,
        )


def transition_task(
    task_id: str,
    from_status: str,
    to_status: str,
    **fields: object,
) -> bool:
    allowed = {
        "queued": {"running", "failed", "cancelled"},
        "running": {"planning", "branch_created", "changes_applied", "failed", "cancelled"},
        "planning": {"branch_created", "failed", "cancelled"},
        "branch_created": {"committed", "failed", "cancelled"},
        "committed": {"pr_created", "failed", "cancelled"},
        "pr_created": {"completed", "failed", "cancelled"},
        "changes_applied": {"completed", "failed", "cancelled"},
    }
    if to_status not in allowed.get(from_status, set()):
        return False

    with SessionLocal() as db:
        task = db.scalar(
            select(Task)
            .where(Task.id == task_id)
            .with_for_update()
        )
        if not task or task.status != from_status:
            return False

        task.status = to_status
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        if to_status in {"completed", "failed", "cancelled"}:
            task.completed_at = _now()
        db.commit()
        return True


def complete_task(
    task_id: str,
    model: str,
    credits_used: int | None = None,
) -> None:
    with SessionLocal() as db:
        usage = db.scalar(
            select(UsageRecord)
            .where(UsageRecord.task_id == task_id)
            .with_for_update()
        )
        if not usage:
            raise BillingError("Usage record is missing")

        task = db.scalar(
            select(Task)
            .where(Task.id == task_id)
            .with_for_update()
        )
        if not task:
            raise BillingError("Task record is missing")

        if usage.status != "reserved":
            if usage.status == "completed":
                return
            raise BillingError("Usage record is not reservable")

        usage.model = model[:255]
        usage.credits_used = (
            usage.credits_reserved
            if credits_used is None
            else max(0, min(credits_used, usage.credits_reserved))
        )
        usage.status = "completed"

        if task.status not in {"completed", "failed", "cancelled"}:
            task.status = "completed"
            task.model = model[:255]
            task.completed_at = _now()

        db.commit()


def fail_task(
    task_id: str,
    model: str,
    reason: str = "failed",
    *,
    refund: bool = True,
) -> None:
    """Fail a task and optionally refund its reservation.

    Refunds are allowed only when no external GitHub side effect was created.
    """
    with SessionLocal() as db:
        usage = db.scalar(
            select(UsageRecord)
            .where(UsageRecord.task_id == task_id)
            .with_for_update()
        )
        if not usage or usage.status != "reserved":
            return

        user = db.get(User, usage.user_id, with_for_update=True)
        task = db.scalar(
            select(Task)
            .where(Task.id == task_id)
            .with_for_update()
        )

        if refund and user:
            user.credits += usage.credits_reserved

        usage.model = model[:255]
        usage.credits_used = 0 if refund else usage.credits_reserved
        usage.status = reason[:32]

        if task and task.status not in {"completed", "failed", "cancelled"}:
            task.status = "failed"
            task.model = model[:255]
            task.error = reason[:4000]
            task.completed_at = _now()

        db.commit()
