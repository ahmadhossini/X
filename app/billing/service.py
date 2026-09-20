from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.billing.ton import TonPaymentIntent, TonPaymentService
from core.config import settings
from database.models import Payment, Subscription, User


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

    # Serialize payment creation per user. Without this lock, two concurrent
    # clicks can create two pending invoices with different memos.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
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
        existing = db.scalar(
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.plan == plan_key,
                Payment.status == "pending",
            )
            .order_by(Payment.created_at.desc())
        )
        if existing is None:
            raise BillingServiceError("Unable to create payment intent") from exc
        return TonPaymentIntent(
            payment_id=existing.id,
            amount_nano_ton=existing.amount_nano_ton,
            destination=existing.destination,
            memo=existing.memo,
        )
    return intent


def create_pro_payment(db: Session, user_id: int) -> TonPaymentIntent:
    return create_plan_payment(db, user_id, "pro")


def confirm_verified_payment(db: Session, payment_id: str, tx_hash: str) -> None:
    tx_hash = tx_hash.strip()
    if not tx_hash:
        raise BillingServiceError("Transaction hash is required")

    # The payment row is the serialization point for confirmation. All state
    # changes below happen in this one DB transaction.
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

    # tx_hash has a UNIQUE constraint in database.models. The explicit lookup
    # provides a clear application error; the constraint is the final race-safe
    # protection against two payment intents consuming the same transaction.
    duplicate = db.scalar(
        select(Payment).where(
            Payment.tx_hash == tx_hash,
            Payment.id != payment_id,
        )
    )
    if duplicate is not None:
        raise BillingServiceError("Transaction was already used")

    user = db.scalar(select(User).where(User.id == payment.user_id).with_for_update())
    if user is None:
        raise BillingServiceError("User not found")

    subscription = db.scalar(
        select(Subscription).where(Subscription.user_id == user.id).with_for_update()
    )
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            plan="free",
            status="active",
        )
        db.add(subscription)
        db.flush()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=30)

    # Preserve remaining paid time when the same plan is renewed.
    if (
        payment.plan != "free"
        and subscription.plan == payment.plan
        and subscription.status == "active"
        and subscription.expires_at
        and subscription.expires_at > now
    ):
        expires_at = subscription.expires_at + timedelta(days=30)

    plan = PLANS.get(payment.plan)
    if plan is None:
        raise BillingServiceError("Payment references an unknown plan")

    payment.tx_hash = tx_hash
    payment.status = "confirmed"
    payment.confirmed_at = now

    subscription.plan = payment.plan
    subscription.status = "active"
    subscription.starts_at = now
    subscription.expires_at = expires_at

    user.plan = payment.plan
    user.credits = plan.monthly_credits
    user.credits_reset_at = expires_at

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BillingServiceError("Transaction was already used") from exc
