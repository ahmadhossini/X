from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.billing.subscriptions import activate_plan
from app.billing.ton import TonPaymentIntent, TonPaymentService
from core.config import settings
from database.models import Payment, User


class BillingServiceError(RuntimeError):
    pass


def _price_for_plan(plan_key: str) -> int:
    if plan_key == "pro":
        return settings.ton_pro_price_nano_ton
    if plan_key == "team":
        return settings.ton_team_price_nano_ton
    raise BillingServiceError(f"Unsupported paid plan: {plan_key}")


def create_plan_payment(db: Session, user_id: int, plan_key: str) -> TonPaymentIntent:
    plan = PLANS.get(plan_key)
    if plan is None or plan_key == "free":
        raise BillingServiceError("Paid plan is not configured")

    user = db.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    if user is None:
        raise BillingServiceError("User not found")

    amount = _price_for_plan(plan_key)
    existing = db.scalar(
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.plan == plan_key,
            Payment.status == "pending",
        )
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return TonPaymentIntent(
            payment_id=existing.id,
            amount_nano_ton=existing.amount_nano_ton,
            destination=existing.destination,
            memo=existing.memo,
        )

    payment_id = uuid4().hex
    intent = TonPaymentService(settings.ton_wallet_address).create_intent(
        payment_id,
        amount,
    )
    db.add(
        Payment(
            id=payment_id,
            user_id=user_id,
            plan=plan_key,
            amount_nano_ton=intent.amount_nano_ton,
            destination=intent.destination,
            memo=intent.memo,
            status="pending",
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BillingServiceError("Unable to create a unique payment intent") from exc
    return intent


def create_pro_payment(db: Session, user_id: int) -> TonPaymentIntent:
    return create_plan_payment(db, user_id, "pro")


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
        select(Payment)
        .where(Payment.tx_hash == tx_hash, Payment.id != payment_id)
        .with_for_update()
    )
    if duplicate is not None:
        raise BillingServiceError("Transaction was already used")

    payment.tx_hash = tx_hash
    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)

    try:
        activate_plan(
            db,
            payment.user_id,
            payment.plan,
            datetime.now(timezone.utc) + timedelta(days=30),
        )
    except IntegrityError as exc:
        db.rollback()
        raise BillingServiceError(
            "Payment could not be committed safely; no subscription was activated"
        ) from exc
