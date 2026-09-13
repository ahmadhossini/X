from __future__ import annotations

import httpx

from billing.plans import get_plan
from core.config import settings

BASE_URL = "https://pay.crypt.bot/api"


class CryptoPayError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    token = settings.crypto_pay_api_token
    if not token:
        raise CryptoPayError("CRYPTO_PAY_API_TOKEN is not configured")
    return {"Crypto-Pay-API-Token": token}


def create_invoice(telegram_id: int, plan_key: str) -> dict:
    plan = get_plan(plan_key)
    payload = {
        "currency_type": "fiat",
        "fiat": "USD",
        "amount": str(plan.price_usd),
        "accepted_assets": "USDT,TON",
        "description": f"XAI Code Agent - {plan.title} - {plan.credits} Credits",
        "payload": f"{telegram_id}:{plan.key}",
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 1800,
    }
    with httpx.Client(timeout=15) as client:
        response = client.post(f"{BASE_URL}/createInvoice", headers=_headers(), json=payload)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise CryptoPayError(str(data.get("error") or "Crypto Pay rejected the invoice"))
    return data["result"]


def get_invoice(invoice_id: int) -> dict | None:
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{BASE_URL}/getInvoices",
            headers=_headers(),
            params={"invoice_ids": str(invoice_id)},
        )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise CryptoPayError(str(data.get("error") or "Crypto Pay request failed"))
    items = (data.get("result") or {}).get("items") or []
    return items[0] if items else None
