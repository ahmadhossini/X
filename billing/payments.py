from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from billing.plans import Plan, get_plan
from database.models import Payment, Subscription, User
from database.session import SessionLocal


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sync_total_credits(user: User) -> None:
    user.subscription_credits = max(0, user.subscription_credits)
    user.topup_credits = max(0, user.topup_credits)
    user.credits = user.subscription_credits + user.topup_credits


def _load_existing_payment(db, provider: str, payment_id: str, user_id: int) -> Payment | None:
    """Load a payment idempotently and prevent cross-user payment-id reuse."""
    existing = db.scalar(
        select(Payment)
        .where(
            Payment.provider == provider,
            Payment.provider_payment_id == payment_id,
        )
        .with_for_update()
    )
    if existing and existing.user_id != user_id:
        raise ValueError("Payment belongs to another user")
    return existing


def activate_paid_plan(
    telegram_id: int,
    plan_key: str,
    payment_method: str,
    payment_id: str,
    amount_usd_cents: int,
    *,
    asset: str = "USD",
    raw_payload: dict | None = None,
) -> bool:
    """Atomically record a payment and grant credits exactly once."""
    plan: Plan = get_plan(plan_key)
    if not plan.subscription:
        return activate_topup(
            telegram_id,
            plan_key,
            payment_method,
            payment_id,
            amount_usd_cents,
            asset=asset,
            raw_payload=raw_payload,
        )

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if not user:
            raise ValueError("User not found")

        existing = _load_existing_payment(db, payment_method, payment_id, user.id)
        if existing and existing.status == "paid":
            return False

        now = _now()
        active_sub = db.scalar(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.active.is_(True),
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
            .with_for_update()
        )
        starts_at = max(now, active_sub.expires_at) if active_sub else now
        expires_at = starts_at + timedelta(days=plan.duration_days)
        subscription = Subscription(
            user_id=user.id,
            plan=plan.key,
            credits_granted=plan.credits,
            starts_at=starts_at,
            expires_at=expires_at,
            payment_method=payment_method,
            payment_id=payment_id,
            active=True,
        )

        user.plan = plan.key
        user.subscription_credits += plan.credits
        user.credits_reset_at = expires_at
        _sync_total_credits(user)
        _record_payment(
            db,
            user.id,
            payment_method,
            payment_id,
            plan.key,
            amount_usd_cents,
            asset,
            raw_payload,
            existing,
            now,
        )
        db.add(subscription)
        db.commit()
        return True


def activate_topup(
    telegram_id: int,
    plan_key: str,
    payment_method: str,
    payment_id: str,
    amount_usd_cents: int,
    *,
    asset: str = "USD",
    raw_payload: dict | None = None,
) -> bool:
    """Grant a non-expiring top-up package once, without changing subscription."""
    plan = get_plan(plan_key)
    if plan.subscription:
        raise ValueError("Plan is not a top-up")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if not user:
            raise ValueError("User not found")
        existing = _load_existing_payment(db, payment_method, payment_id, user.id)
        if existing and existing.status == "paid":
            return False

        now = _now()
        user.topup_credits += plan.credits
        _sync_total_credits(user)
        _record_payment(
            db,
            user.id,
            payment_method,
            payment_id,
            plan.key,
            amount_usd_cents,
            asset,
            raw_payload,
            existing,
            now,
        )
        db.commit()
        return True


def _record_payment(
    db,
    user_id: int,
    provider: str,
    payment_id: str,
    plan_key: str,
    amount_usd_cents: int,
    asset: str,
    raw_payload: dict | None,
    existing: Payment | None,
    now: datetime,
) -> None:
    amount_usd = int(round(amount_usd_cents / 100))
    payload = json.dumps(raw_payload or {}, ensure_ascii=False)[:20000]
    if existing:
        existing.status = "paid"
        existing.plan = plan_key
        existing.amount_usd = amount_usd
        existing.amount_usd_cents = amount_usd_cents
        existing.asset = asset
        existing.raw_payload = payload
        existing.paid_at = now
    else:
        db.add(
            Payment(
                user_id=user_id,
                provider=provider,
                provider_payment_id=payment_id,
                plan=plan_key,
                amount_usd=amount_usd,
                amount_usd_cents=amount_usd_cents,
                asset=asset,
                status="paid",
                raw_payload=payload,
                paid_at=now,
            )
        )
