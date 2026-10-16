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
    now = utcnow()
    if plan_key != "free" and subscription.plan == plan_key and subscription.status == "active" and subscription.expires_at and subscription.expires_at > now and expires_at:
        expires_at = subscription.expires_at + (expires_at - now)
    subscription.plan = plan_key
    subscription.status = "active"
    subscription.starts_at = now
    subscription.expires_at = expires_at
    user.plan = plan_key
    user.credits = PLANS[plan_key].monthly_credits
    user.credits_reset_at = expires_at
    db.commit()
    db.refresh(subscription)
    return subscription


def expire_user_plan_in_session(db: Session, user: User, now: datetime | None = None) -> bool:
    """Downgrade an expired paid plan without committing the caller's transaction."""
    if user.plan == "free":
        return False

    now = now or utcnow()
    subscription = db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .with_for_update()
    )
    if (
        subscription is None
        or subscription.plan == "free"
        or subscription.expires_at is None
        or subscription.expires_at > now
    ):
        return False

    subscription.plan = "free"
    subscription.status = "expired"
    subscription.expires_at = now
    user.plan = "free"
    user.credits = 0
    user.credits_reset_at = now
    return True


def expire_subscription_if_needed(db: Session, user_id: int) -> bool:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        return False
    changed = expire_user_plan_in_session(db, user)
    if changed:
        db.commit()
    return changed
