from __future__ import annotations

import base64
import hashlib
import hmac
import httpx
import time

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


def make_checkout_token(telegram_id: int, plan_key: str, ttl_seconds: int = 900) -> str:
    if not settings.crypto_pay_webhook_secret:
        raise CryptoPayError("CRYPTO_PAY_WEBHOOK_SECRET is not configured")
    get_plan(plan_key)
    expires = int(time.time()) + ttl_seconds
    body = f"{telegram_id}:{plan_key}:{expires}"
    signature = hmac.new(settings.crypto_pay_webhook_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    raw = f"{body}:{signature}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def verify_checkout_token(token: str) -> tuple[int, str]:
    if not settings.crypto_pay_webhook_secret:
        raise CryptoPayError("CRYPTO_PAY_WEBHOOK_SECRET is not configured")
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        telegram_id_text, plan_key, expires_text, signature = decoded.split(":", 3)
        body = f"{telegram_id_text}:{plan_key}:{expires_text}"
        expected = hmac.new(settings.crypto_pay_webhook_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_text) < int(time.time()):
            raise ValueError
        return int(telegram_id_text), plan_key
    except (ValueError, TypeError, UnicodeError, base64.binascii.Error) as exc:
        raise CryptoPayError("Invalid or expired checkout token") from exc


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
