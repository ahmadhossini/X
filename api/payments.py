from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from billing.crypto import create_invoice, verify_checkout_token
from billing.payments import activate_paid_plan
from billing.plans import get_plan
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/crypto/checkout")
def crypto_checkout(token: str) -> RedirectResponse:
    try:
        telegram_id, plan_key = verify_checkout_token(token)
        invoice = create_invoice(telegram_id, plan_key)
        url = invoice.get("web_app_invoice_url") or invoice.get("bot_invoice_url")
        if not url:
            raise RuntimeError("Crypto invoice URL missing")
        return RedirectResponse(url=url, status_code=307)
    except Exception as exc:
        logger.warning("Crypto checkout creation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Unable to create crypto checkout") from exc


@router.post("/crypto/webhook/{secret}")
def crypto_webhook(secret: str, update: dict) -> dict[str, bool]:
    configured = settings.crypto_pay_webhook_secret
    if not configured or secret != configured:
        raise HTTPException(status_code=404, detail="Not found")

    if update.get("update_type") != "invoice_paid":
        return {"ok": True}

    invoice = update.get("payload") or {}
    if invoice.get("status") != "paid":
        return {"ok": True}

    payload = str(invoice.get("payload") or "")
    try:
        telegram_id_text, plan_key = payload.split(":", 1)
        telegram_id = int(telegram_id_text)
        plan = get_plan(plan_key)
    except (ValueError, TypeError):
        logger.warning("Invalid Crypto Pay invoice payload")
        return {"ok": True}

    if invoice.get("currency_type") != "fiat" or invoice.get("fiat") != "USD":
        logger.warning("Rejected non-USD Crypto Pay invoice")
        return {"ok": True}

    try:
        if int(float(invoice.get("amount") or 0)) != plan.price_usd:
            logger.warning("Rejected Crypto Pay invoice with unexpected amount")
            return {"ok": True}
    except (TypeError, ValueError):
        return {"ok": True}

    invoice_id = invoice.get("invoice_id")
    if not invoice_id:
        return {"ok": True}

    paid_asset = str(invoice.get("paid_asset") or invoice.get("asset") or "USDT")
    try:
        activated = activate_paid_plan(
            telegram_id,
            plan_key,
            "cryptopay",
            str(invoice_id),
            plan.price_usd,
            asset=paid_asset,
            raw_payload=invoice,
        )
    except Exception:
        logger.exception("Crypto Pay activation failed for invoice %s", invoice_id)
        raise HTTPException(status_code=500, detail="Payment processing failed")

    logger.info("Crypto Pay invoice %s processed; activated=%s", invoice_id, activated)
    return {"ok": True}
