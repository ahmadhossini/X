from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from api.miniapp import _auth_user, _init_data
from app.billing.stars import StarsPaymentError, stars_amount_for_plan
from core.config import settings
from database.models import StarsPayment
from database.session import SessionLocal

router = APIRouter(prefix="/api/payments", tags=["payments"])


async def _create_stars_invoice(plan_key: str, authorization: str | None, x_telegram_init_data: str | None) -> dict[str, str | int]:
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    if not settings.bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")
    try:
        amount = stars_amount_for_plan(plan_key, settings)
    except StarsPaymentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    payment_id = uuid4().hex
    payload = f"xai:{payment_id}:{plan_key}:{user.telegram_id}"
    with SessionLocal() as db:
        # Expire older pending invoices for the same plan so stale invoices cannot be reused.
        db.query(StarsPayment).filter(
            StarsPayment.user_id == user.id,
            StarsPayment.plan == plan_key,
            StarsPayment.status == "pending",
        ).update({"status": "expired"})
        payment = StarsPayment(
            id=payment_id,
            user_id=user.id,
            telegram_id=user.telegram_id,
            plan=plan_key,
            currency="XTR",
            amount_stars=amount,
            invoice_payload=payload,
            status="pending",
        )
        db.add(payment)
        db.commit()

    invoice = {
        "title": f"XAI Code Agent — {plan_key.title()}",
        "description": f"{plan_key.title()} subscription for 30 days",
        "payload": payload,
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": f"{plan_key.title()} subscription", "amount": amount}],
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/createInvoiceLink",
                json=invoice,
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("ok") or not data.get("result"):
            raise RuntimeError("Telegram did not return an invoice link")
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        with SessionLocal() as db:
            current = db.scalar(select(StarsPayment).where(StarsPayment.id == payment_id))
            if current and current.status == "pending":
                current.status = "failed"
                db.commit()
        raise HTTPException(status_code=502, detail="Could not create Telegram Stars invoice") from exc

    return {
        "payment_id": payment_id,
        "plan": plan_key,
        "currency": "XTR",
        "amount_stars": amount,
        "invoice_url": str(data["result"]),
        "status": "pending",
    }


@router.post("/stars/pro")
async def create_stars_pro_payment(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int]:
    return await _create_stars_invoice("pro", authorization, x_telegram_init_data)


@router.post("/stars/team")
async def create_stars_team_payment(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int]:
    return await _create_stars_invoice("team", authorization, x_telegram_init_data)
