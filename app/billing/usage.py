from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from database.models import User


class UsageLimitExceeded(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UsageDecision:
    allowed: bool
    remaining: int
    plan: str


def consume_credit(db: Session, user_id: int, amount: int = 1) -> UsageDecision:
    if amount <= 0:
        raise ValueError("amount must be positive")
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    plan = PLANS.get(user.plan, PLANS["free"])
    now = datetime.now(timezone.utc)
    if user.credits_reset_at is None or user.credits_reset_at <= now:
        user.credits = plan.monthly_credits
        user.credits_reset_at = now
    if user.credits < amount:
        raise UsageLimitExceeded("usage limit reached")
    user.credits -= amount
    db.commit()
    return UsageDecision(True, user.credits, plan.key)
