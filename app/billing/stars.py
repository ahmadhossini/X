from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.billing.subscriptions import activate_plan
from database.models import StarsPayment


class StarsPaymentError(RuntimeError):
    pass


def stars_amount_for_plan(plan_key: str, settings) -> int:
    if plan_key == "pro":
        amount = settings.stars_pro_amount
    elif plan_key == "team":
        amount = settings.stars_team_amount
    else:
        raise StarsPaymentError(f"Unsupported paid plan: {plan_key}")
    if plan_key not in PLANS or amount <= 0:
        raise StarsPaymentError(f"Stars amount is not configured for plan: {plan_key}")
    return amount


def validate_stars_precheckout(db: Session, payload: str, telegram_id: int, currency: str, total_amount: int) -> bool:
    payment = db.scalar(select(StarsPayment).where(StarsPayment.invoice_payload == payload).with_for_update())
    return bool(
        payment
        and payment.status == "pending"
        and payment.telegram_id == telegram_id
        and currency == "XTR"
        and total_amount == payment.amount_stars
    )


def confirm_stars_payment(
    db: Session,
    payment_id: str,
    telegram_id: int,
    currency: str,
    total_amount: int,
    charge_id: str,
    provider_charge_id: str | None = None,
) -> None:
    charge_id = charge_id.strip()
    if not charge_id:
        raise StarsPaymentError("Telegram payment charge ID is required")
    payment = db.scalar(select(StarsPayment).where(StarsPayment.id == payment_id).with_for_update())
    if payment is None:
        raise StarsPaymentError("Stars payment not found")
    if payment.status == "confirmed":
        if payment.telegram_payment_charge_id != charge_id:
            raise StarsPaymentError("Stars payment is already confirmed with another charge")
        return
    if payment.status != "pending":
        raise StarsPaymentError("Stars payment is not pending")
    if payment.telegram_id != telegram_id or currency != "XTR" or total_amount != payment.amount_stars:
        raise StarsPaymentError("Stars payment details do not match the invoice")
    duplicate = db.scalar(
        select(StarsPayment).where(
            StarsPayment.telegram_payment_charge_id == charge_id,
            StarsPayment.id != payment_id,
        ).with_for_update()
    )
    if duplicate is not None:
        raise StarsPaymentError("Telegram payment charge was already used")
    payment.telegram_payment_charge_id = charge_id
    payment.provider_payment_charge_id = provider_charge_id
    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)
    try:
        activate_plan(db, payment.user_id, payment.plan, datetime.now(timezone.utc) + timedelta(days=30))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise StarsPaymentError("Payment could not be committed safely; no subscription was activated") from exc
