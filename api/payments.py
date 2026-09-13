from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from billing.payments import activate_paid_plan
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


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
    except (ValueError, TypeError):
        logger.warning("Invalid Crypto Pay invoice payload")
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
            int(float(invoice.get("amount") or 0)),
            asset=paid_asset,
            raw_payload=invoice,
        )
    except Exception:
        logger.exception("Crypto Pay activation failed for invoice %s", invoice_id)
        raise HTTPException(status_code=500, detail="Payment processing failed")

    logger.info("Crypto Pay invoice %s processed; activated=%s", invoice_id, activated)
    return {"ok": True}
