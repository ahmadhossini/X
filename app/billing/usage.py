from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from core.config import settings
from database.models import User


class UsageLimitExceeded(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UsageDecision:
    allowed: bool
    remaining: int
    plan: str


def _credits_for_plan(plan_key: str) -> int:
    if plan_key == "free":
        return settings.free_monthly_credits
    if plan_key == "pro":
        return settings.pro_monthly_credits
    return PLANS.get(plan_key, PLANS["free"]).monthly_credits


def consume_credit(db: Session, user_id: int, amount: int = 1) -> UsageDecision:
    if amount <= 0:
        raise ValueError("amount must be positive")

    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    plan = PLANS.get(user.plan, PLANS["free"])
    now = datetime.now(timezone.utc)

    if user.credits_reset_at is None or user.credits_reset_at <= now:
        user.credits = _credits_for_plan(plan.key)
        user.credits_reset_at = now + timedelta(days=30)

    if user.credits < amount:
        raise UsageLimitExceeded("usage limit reached")

    user.credits -= amount
    db.commit()
    return UsageDecision(True, user.credits, plan.key)
