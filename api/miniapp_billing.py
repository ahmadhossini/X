from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from billing.stars import STAR_PRICES, StarsPaymentError, create_invoice_link
from billing.ton import TonPaymentError, create_usdt_order
from billing.plans import PLANS, get_plan
from api.miniapp import _auth_user, _init_data

router = APIRouter(prefix="/api/miniapp/billing", tags=["miniapp-billing"])


class PlanRequest(BaseModel):
    plan: str = Field(min_length=2, max_length=32)


@router.get("/plans")
def plans(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    _auth_user(_init_data(authorization, x_telegram_init_data))
    return {
        "plans": [
            {
                "key": plan.key,
                "title": plan.title,
                "price_usd": f"{plan.price_usd:.2f}",
                "duration_days": plan.duration_days,
                "credits": plan.credits,
                "subscription": plan.subscription,
                "stars": STAR_PRICES[plan.key],
            }
            for plan in PLANS.values()
        ],
        "crypto_asset": "USDT",
        "crypto_network": "TON",
    }


@router.post("/stars")
def stars(
    payload: PlanRequest,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str | int]:
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    try:
        plan = get_plan(payload.plan)
        url = create_invoice_link(user.telegram_id, plan.key)
    except (ValueError, KeyError, StarsPaymentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plan": plan.key, "stars": STAR_PRICES[plan.key], "invoice_url": url}


@router.post("/crypto")
def crypto(
    payload: PlanRequest,
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    try:
        return create_usdt_order(user.telegram_id, payload.plan)
    except (ValueError, KeyError, TonPaymentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
