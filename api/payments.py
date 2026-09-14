from __future__ import annotations

import html
import logging
import threading
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from billing.ton import TonPaymentError, get_usdt_order, verify_usdt_order
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

_TON_STATUS_MIN_INTERVAL = 3.0
_ton_status_lock = threading.Lock()
_ton_status_last_checked: dict[str, float] = {}
_TON_STATUS_MAX_TRACKED = 10_000


def _allow_ton_status_check(order_id: str) -> bool:
    now = time.monotonic()
    with _ton_status_lock:
        last = _ton_status_last_checked.get(order_id)
        if last is not None and now - last < _TON_STATUS_MIN_INTERVAL:
            return False
        _ton_status_last_checked[order_id] = now
        if len(_ton_status_last_checked) > _TON_STATUS_MAX_TRACKED:
            cutoff = now - 60.0
            stale = [key for key, value in _ton_status_last_checked.items() if value < cutoff]
            for key in stale[:2000]:
                _ton_status_last_checked.pop(key, None)
        return True


@router.get("/ton/checkout/{order_id}", response_class=HTMLResponse)
def ton_checkout(order_id: str) -> str:
    if len(order_id) > 80 or not order_id.startswith("ton-"):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        details = get_usdt_order(order_id)
    except TonPaymentError as exc:
        raise HTTPException(status_code=404, detail="Payment order not found") from exc
    return _checkout_html(order_id, details)


@router.get("/ton/status/{order_id}")
def ton_status(order_id: str) -> dict:
    if len(order_id) > 80 or not order_id.startswith("ton-"):
        raise HTTPException(status_code=404, detail="Not found")
    if not _allow_ton_status_check(order_id):
        raise HTTPException(status_code=429, detail="Please wait before checking this payment again")
    try:
        return verify_usdt_order(order_id)
    except TonPaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Direct TON payment verification failed for %s", order_id)
        raise HTTPException(status_code=502, detail="Payment verification is temporarily unavailable") from exc


def _checkout_html(order_id: str, details: dict) -> str:
    safe_order = html.escape(order_id, quote=True)
    address = html.escape(str(details.get("address") or ""), quote=True)
    amount = html.escape(str(details.get("amount_usdt") or ""), quote=True)
    comment = html.escape(str(details.get("comment") or ""), quote=True)
    deep_link = html.escape(str(details.get("deep_link") or "#"), quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAI Code Agent Payment</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f6f9;color:#172033;margin:0;padding:24px}}
.card{{max-width:520px;margin:20px auto;background:#fff;border:1px solid #e4e8ee;border-radius:18px;padding:22px;box-shadow:0 2px 10px rgba(16,24,40,.05)}}
.value{{background:#f7f8fa;border-radius:12px;padding:12px;word-break:break-all;margin:8px 0 14px}}
button,a{{display:block;width:100%;box-sizing:border-box;border:0;border-radius:12px;padding:13px 15px;font:inherit;font-weight:700;text-align:center;text-decoration:none;cursor:pointer;margin-top:10px}}
a{{background:#172033;color:#fff}}button{{background:#edf0f4;color:#263246}}
small{{color:#667085;line-height:1.6}}#status{{margin-top:16px;padding:12px;border-radius:12px;background:#f7f8fa}}
</style>
</head>
<body>
<div class="card">
<h1>USDT payment</h1>
<p>Send the exact amount of USDT on the TON network and include the payment comment.</p>
<div><strong>Order</strong><div class="value">{safe_order}</div></div>
<div><strong>Payment address</strong><div id="address" class="value">{address}</div></div>
<div><strong>Amount</strong><div id="amount" class="value">{amount} USDT</div></div>
<div><strong>Comment</strong><div id="comment" class="value">{comment}</div></div>
<a id="wallet" href="{deep_link}">Open TON wallet</a>
<button id="copy">Copy payment details</button>
<div id="status">Checking payment...</div>
<small>Do not send another asset or another network. Credits are added only after the blockchain transaction is verified.</small>
</div>
<script>
const statusUrl = {("/api/payments/ton/status/" + safe_order)!r};
async function load() {{
  const response = await fetch(statusUrl);
  const data = await response.json();
  if (data.status === 'paid') {{
    document.getElementById('status').textContent = 'Payment confirmed. Credits have been added.';
    return true;
  }}
  if (data.status === 'expired') {{
    document.getElementById('status').textContent = 'This payment order has expired.';
    return true;
  }}
  return false;
}}
document.getElementById('copy').onclick = async () => {{
  await navigator.clipboard.writeText(`USDT on TON\nAddress: {address}\nAmount: {amount}\nComment: {comment}`);
  document.getElementById('copy').textContent = 'Copied';
}};
load();
setInterval(() => load().catch(() => {{}}), 5000);
</script>
</body>
</html>"""
