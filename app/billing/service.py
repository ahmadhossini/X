from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.billing.subscriptions import activate_plan
from app.billing.ton import TonPaymentIntent, TonPaymentService
from core.config import settings
from database.models import Payment


class BillingServiceError(RuntimeError):
    pass


def create_pro_payment(db: Session, user_id: int) -> TonPaymentIntent:
    if "pro" not in PLANS:
        raise BillingServiceError("Pro plan is not configured")
    payment_id = uuid4().hex
    intent = TonPaymentService(settings.ton_wallet_address).create_intent(
        payment_id,
        settings.ton_pro_price_nano_ton,
    )
    db.add(
        Payment(
            id=payment_id,
            user_id=user_id,
            plan="pro",
            amount_nano_ton=intent.amount_nano_ton,
            destination=intent.destination,
            memo=intent.memo,
            status="pending",
        )
    )
    db.commit()
    return intent


def confirm_verified_payment(db: Session, payment_id: str, tx_hash: str) -> None:
    tx_hash = tx_hash.strip()
    if not tx_hash:
        raise BillingServiceError("Transaction hash is required")

    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        raise BillingServiceError("Payment not found")
    if payment.status == "confirmed":
        if payment.tx_hash != tx_hash:
            raise BillingServiceError("Payment is already confirmed")
        return
    if payment.status != "pending":
        raise BillingServiceError("Payment is not pending")

    duplicate = db.scalar(
        select(Payment).where(Payment.tx_hash == tx_hash, Payment.id != payment_id)
    )
    if duplicate is not None:
        raise BillingServiceError("Transaction was already used")

    payment.tx_hash = tx_hash
    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)
    activate_plan(
        db,
        payment.user_id,
        payment.plan,
        datetime.now(timezone.utc) + timedelta(days=30),
    )
