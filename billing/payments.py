from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from billing.plans import Plan, get_plan
from database.models import Payment, Subscription, User
from database.session import SessionLocal


def _now() -> datetime:
    return datetime.now(timezone.utc)


def activate_paid_plan(
    telegram_id: int,
    plan_key: str,
    payment_method: str,
    payment_id: str,
    amount_usd: int,
    *,
    asset: str = "USD",
    raw_payload: dict | None = None,
) -> bool:
    """Atomically record a payment and grant the plan once.

    Provider payment IDs are unique, so webhook retries cannot double-grant credits.
    """
    plan: Plan = get_plan(plan_key)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if not user:
            raise ValueError("User not found")

        existing = db.scalar(
            select(Payment).where(
                Payment.provider == payment_method,
                Payment.provider_payment_id == payment_id,
            ).with_for_update()
        )
        if existing and existing.status == "paid":
            return False

        now = _now()
        active_sub = db.scalar(
            select(Subscription)
            .where(Subscription.user_id == user.id, Subscription.active.is_(True), Subscription.expires_at > now)
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
        user.credits += plan.credits
        user.credits_reset_at = expires_at

        if existing:
            existing.status = "paid"
            existing.plan = plan.key
            existing.amount_usd = amount_usd
            existing.asset = asset
            existing.raw_payload = json.dumps(raw_payload or {}, ensure_ascii=False)[:20000]
            existing.paid_at = now
        else:
            db.add(Payment(
                user_id=user.id,
                provider=payment_method,
                provider_payment_id=payment_id,
                plan=plan.key,
                amount_usd=amount_usd,
                asset=asset,
                status="paid",
                raw_payload=json.dumps(raw_payload or {}, ensure_ascii=False)[:20000],
                paid_at=now,
            ))
        db.add(subscription)
        db.commit()
        return True
