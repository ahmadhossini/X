from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from database.models import Subscription, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_subscription(db: Session, user_id: int) -> Subscription:
    subscription = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if subscription is None:
        subscription = Subscription(user_id=user_id, plan="free", status="active")
        db.add(subscription)
        db.flush()
    return subscription


def activate_plan(db: Session, user_id: int, plan_key: str, expires_at: datetime | None) -> Subscription:
    if plan_key not in PLANS:
        raise ValueError(f"Unknown plan: {plan_key}")
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ValueError("User not found")
    subscription = get_or_create_subscription(db, user_id)
    subscription.plan = plan_key
    subscription.status = "active"
    subscription.starts_at = utcnow()
    subscription.expires_at = expires_at
    user.plan = plan_key
    user.credits = PLANS[plan_key].monthly_credits
    user.credits_reset_at = expires_at
    db.commit()
    db.refresh(subscription)
    return subscription


def expire_subscription_if_needed(db: Session, user_id: int) -> bool:
    subscription = db.scalar(select(Subscription).where(Subscription.user_id == user_id).with_for_update())
    if subscription is None or subscription.plan == "free":
        return False
    now = utcnow()
    if subscription.expires_at is None or subscription.expires_at > now:
        return False
    subscription.plan = "free"
    subscription.status = "expired"
    subscription.expires_at = now
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is not None:
        user.plan = "free"
        user.credits = 0
        user.credits_reset_at = now
    db.commit()
    return True
