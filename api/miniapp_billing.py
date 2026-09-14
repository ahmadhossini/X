from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.miniapp import _auth_user, _init_data
from billing.plans import PLANS
from billing.ton import TonPaymentError, create_usdt_order, get_usdt_order

router = APIRouter(prefix="/api/miniapp/billing", tags=["miniapp-billing"])


class PlanRequest(BaseModel):
    plan: str = Field(min_length=2, max_length=32)


def _require_user(
    authorization: str | None,
    x_telegram_init_data: str | None,
):
    return _auth_user(_init_data(authorization, x_telegram_init_data))


@router.get("/plans")
def plans(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    _require_user(authorization, x_telegram_init_data)
    return {
        "plans": [
            {
                "key": plan.key,
                "title": plan.title,
                "price_usd": f"{plan.price_usd:.2f}",
                "duration_days": plan.duration_days,
                "credits": plan.credits,
                "subscription": plan.subscription,
            }
            for plan in PLANS.values()
        ],
        "crypto_asset": "USDT",
        "crypto_network": "TON",
    }


@router.post("/crypto")
def crypto(
    payload: PlanRequest,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    user = _require_user(authorization, x_telegram_init_data)
    try:
        return create_usdt_order(user.telegram_id, payload.plan)
    except (ValueError, KeyError, TonPaymentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/order/{order_id}")
def order_details(
    order_id: str,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    user = _require_user(authorization, x_telegram_init_data)
    if len(order_id) > 80 or not order_id.startswith("ton-"):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return get_usdt_order(order_id, telegram_id=user.telegram_id)
    except TonPaymentError as exc:
        raise HTTPException(status_code=404, detail="Payment order not found") from exc
