from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.billing.service import BillingServiceError, create_pro_payment
from app.billing.ton import TonPaymentService
from core.config import settings
from database.models import User
from database.session import SessionLocal

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentCreateRequest(BaseModel):
    telegram_id: int = Field(gt=0)


@router.post("/ton/pro")
def create_ton_pro_payment(payload: PaymentCreateRequest) -> dict[str, str | int]:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        try:
            intent = create_pro_payment(db, user.id)
        except (BillingServiceError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "payment_id": intent.payment_id,
        "amount_nano_ton": intent.amount_nano_ton,
        "destination": intent.destination,
        "memo": intent.memo,
        "uri": TonPaymentService.to_transfer_uri(
            intent.destination,
            intent.amount_nano_ton,
            intent.memo,
            settings.ton_network,
        ),
        "status": "pending",
    }
