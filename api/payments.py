from __future__ import annotations

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.billing.service import BillingServiceError, confirm_verified_payment, create_plan_payment, create_pro_payment
from app.billing.ton import TonPaymentService
from app.billing.ton_verifier import TonVerificationError, find_payment_transfer
from api.miniapp import _auth_user, _init_data
from core.config import settings
from database.models import Payment
from database.session import SessionLocal

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentVerifyRequest(BaseModel):
    payment_id: str = Field(min_length=16, max_length=64)


def _session(authorization: str | None, x_telegram_init_data: str | None) -> str:
    return _init_data(authorization, x_telegram_init_data)


@router.post("/ton/pro")
def create_ton_pro_payment(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int | float]:
    user = _auth_user(_session(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        try:
            intent = create_pro_payment(db, user.id)
        except (BillingServiceError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            uri = TonPaymentService.to_transfer_uri(
                intent.destination,
                intent.amount_nano_ton,
                intent.memo,
                settings.ton_network,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "payment_id": intent.payment_id,
        "amount_nano_ton": intent.amount_nano_ton,
        "amount_ton": intent.amount_nano_ton / 1_000_000_000,
        "destination": intent.destination,
        "memo": intent.memo,
        "uri": uri,
        "status": "pending",
    }


@router.post("/ton/pro/verify")
async def verify_ton_pro_payment(
    payload: PaymentVerifyRequest,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int | bool | None]:
    user = _auth_user(_session(authorization, x_telegram_init_data))

    with SessionLocal() as db:
        payment = db.scalar(
            select(Payment).where(
                Payment.id == payload.payment_id,
                Payment.user_id == user.id,
            )
        )
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status == "confirmed":
            return {
                "payment_id": payment.id,
                "status": "confirmed",
                "confirmed": True,
                "tx_hash": payment.tx_hash,
            }
        if payment.status != "pending":
            raise HTTPException(status_code=409, detail="Payment is not pending")
        destination = payment.destination
        amount = payment.amount_nano_ton
        memo = payment.memo

    try:
        transfer = await find_payment_transfer(
            destination=destination,
            amount_nano_ton=amount,
            memo=memo,
        )
    except (TonVerificationError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if transfer is None:
        return {
            "payment_id": payload.payment_id,
            "status": "pending",
            "confirmed": False,
            "tx_hash": None,
        }

    with SessionLocal() as db:
        try:
            confirm_verified_payment(db, payload.payment_id, transfer.tx_hash)
        except BillingServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        payment = db.scalar(select(Payment).where(Payment.id == payload.payment_id))
        return {
            "payment_id": payload.payment_id,
            "status": payment.status if payment else "confirmed",
            "confirmed": True,
            "tx_hash": transfer.tx_hash,
        }


@router.post("/ton/team")
def create_ton_team_payment(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int | float]:
    user = _auth_user(_session(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        try:
            intent = create_plan_payment(db, user.id, "team")
        except (BillingServiceError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            uri = TonPaymentService.to_transfer_uri(
                intent.destination,
                intent.amount_nano_ton,
                intent.memo,
                settings.ton_network,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "payment_id": intent.payment_id,
        "amount_nano_ton": intent.amount_nano_ton,
        "amount_ton": intent.amount_nano_ton / 1_000_000_000,
        "destination": intent.destination,
        "memo": intent.memo,
        "uri": uri,
        "status": "pending",
    }


@router.post("/ton/team/verify")
async def verify_ton_team_payment(
    payload: PaymentVerifyRequest,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int | bool | None]:
    user = _auth_user(_session(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        payment = db.scalar(select(Payment).where(Payment.id == payload.payment_id, Payment.user_id == user.id, Payment.plan == "team"))
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status == "confirmed":
            return {"payment_id": payment.id, "status": "confirmed", "confirmed": True, "tx_hash": payment.tx_hash}
        if payment.status != "pending":
            raise HTTPException(status_code=409, detail="Payment is not pending")
        destination, amount, memo = payment.destination, payment.amount_nano_ton, payment.memo
    try:
        transfer = await find_payment_transfer(destination=destination, amount_nano_ton=amount, memo=memo)
    except (TonVerificationError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if transfer is None:
        return {"payment_id": payload.payment_id, "status": "pending", "confirmed": False, "tx_hash": None}
    with SessionLocal() as db:
        try:
            confirm_verified_payment(db, payload.payment_id, transfer.tx_hash)
        except BillingServiceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        payment = db.scalar(select(Payment).where(Payment.id == payload.payment_id))
        return {"payment_id": payload.payment_id, "status": payment.status if payment else "confirmed", "confirmed": True, "tx_hash": transfer.tx_hash}
