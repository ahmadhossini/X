from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from database.models import UsageRecord, User
from database.session import SessionLocal

FREE_DAILY_CREDITS = 5

PLAN_LIMITS = {
    "free": FREE_DAILY_CREDITS,
    "pro": 500,
    "pro_plus": 2000,
}


class BillingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreditReservation:
    task_id: str
    credits: int
    remaining: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _daily_reset_if_needed(user: User, now: datetime) -> None:
    if user.plan != "free":
        return
    if user.credits_reset_at is None or user.credits_reset_at <= now:
        user.credits = FREE_DAILY_CREDITS
        user.credits_reset_at = now + timedelta(days=1)


def ensure_user_credit_state(telegram_id: int) -> tuple[int, str]:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            raise BillingError("User not found")
        now = _now()
        _daily_reset_if_needed(user, now)
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


def reserve_task_credits(telegram_id: int, repository: str, request: str, credits: int) -> CreditReservation:
    if credits <= 0:
        raise BillingError("Invalid credit amount")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            raise BillingError("User not found")
        now = _now()
        _daily_reset_if_needed(user, now)
        if user.credits < credits:
            db.rollback()
            raise BillingError("Insufficient credits")

        user.credits -= credits
        task_id = uuid4().hex
        usage = UsageRecord(
            task_id=task_id,
            user_id=user.id,
            repository=repository,
            request=request[:4000],
            model="",
            credits_reserved=credits,
            credits_used=0,
            status="reserved",
        )
        db.add(usage)
        db.commit()
        return CreditReservation(task_id=task_id, credits=credits, remaining=user.credits)


def complete_task(task_id: str, model: str, credits_used: int | None = None) -> None:
    with SessionLocal() as db:
        usage = db.scalar(select(UsageRecord).where(UsageRecord.task_id == task_id))
        if not usage or usage.status != "reserved":
            raise BillingError("Usage record is not reservable")
        usage.model = model[:255]
        usage.credits_used = usage.credits_reserved if credits_used is None else max(0, credits_used)
        usage.status = "completed"
        db.commit()


def fail_task(task_id: str, model: str, reason: str = "failed") -> None:
    with SessionLocal() as db:
        usage = db.scalar(select(UsageRecord).where(UsageRecord.task_id == task_id))
        if not usage or usage.status != "reserved":
            return
        user = db.get(User, usage.user_id)
        if user:
            user.credits += usage.credits_reserved
        usage.model = model[:255]
        usage.credits_used = 0
        usage.status = reason[:32]
        db.commit()
