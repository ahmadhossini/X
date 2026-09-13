from __future__ import annotations

import json

import httpx

from billing.plans import get_plan
from core.config import settings

STAR_PRICES = {
    "starter": 769,
    "pro": 2307,
    "team": 6154,
    "topup": 384,
}


class StarsPaymentError(RuntimeError):
    pass


def create_invoice_link(telegram_id: int, plan_key: str) -> str:
    plan = get_plan(plan_key)
    stars = STAR_PRICES[plan_key]
    payload = f"{telegram_id}:{plan.key}"
    request = {
        "title": plan.title[:32],
        "description": (
            f"XAI Code Agent: {plan.credits} Credits for {plan.duration_days} days."
            if plan.subscription
            else f"XAI Code Agent: {plan.credits} Credits top-up."
        )[:255],
        "payload": payload,
        "currency": "XTR",
        "prices": json.dumps([
            {"label": f"{plan.title} - {plan.credits} Credits", "amount": stars}
        ]),
        "start_parameter": f"xai-{plan.key}",
    }
    if not settings.bot_token:
        raise StarsPaymentError("BOT_TOKEN is not configured")
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"https://api.telegram.org/bot{settings.bot_token}/createInvoiceLink",
            json=request,
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok") or not data.get("result"):
        raise StarsPaymentError(str(data.get("description") or "Telegram rejected the invoice"))
    return str(data["result"])
