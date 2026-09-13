from __future__ import annotations

import html
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from billing.ton import TonPaymentError, verify_usdt_order
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/ton/checkout/{order_id}", response_class=HTMLResponse)
def ton_checkout(order_id: str) -> str:
    if len(order_id) > 80 or not order_id.startswith("ton-"):
        raise HTTPException(status_code=404, detail="Not found")
    return _checkout_html(order_id)


@router.get("/ton/status/{order_id}")
def ton_status(order_id: str) -> dict:
    if len(order_id) > 80 or not order_id.startswith("ton-"):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return verify_usdt_order(order_id)
    except TonPaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Direct TON payment verification failed for %s", order_id)
        raise HTTPException(status_code=502, detail="Payment verification is temporarily unavailable") from exc


def _checkout_html(order_id: str) -> str:
    safe_order = html.escape(order_id, quote=True)
    status_url = f"{settings.public_base_url}/api/payments/ton/status/{safe_order}"
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
<div><strong>Payment address</strong><div id="address" class="value">Loading...</div></div>
<div><strong>Amount</strong><div id="amount" class="value">Loading...</div></div>
<div><strong>Comment</strong><div id="comment" class="value">Loading...</div></div>
<a id="wallet" href="#">Open TON wallet</a>
<button id="copy">Copy payment details</button>
<div id="status">Checking payment...</div>
<small>Do not send another asset or another network. Credits are added only after the blockchain transaction is verified.</small>
</div>
<script>
const orderId = {order_id!r};
const statusUrl = {status_url!r};
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
async function init() {{
  const response = await fetch(statusUrl.replace('/status/', '/checkout/').replace('/api/payments/ton/checkout/', '/api/miniapp/billing/order/'));
  if (!response.ok) return;
}}
fetch('/api/miniapp/billing/order/' + encodeURIComponent(orderId)).then(r => r.json()).then(data => {{
  document.getElementById('address').textContent = data.address || '';
  document.getElementById('amount').textContent = (data.amount_usdt || '') + ' USDT';
  document.getElementById('comment').textContent = data.comment || '';
  document.getElementById('wallet').href = data.deep_link || '#';
  document.getElementById('copy').onclick = async () => {{
    await navigator.clipboard.writeText(`USDT on TON\nAddress: ${{data.address}}\nAmount: ${{data.amount_usdt}}\nComment: ${{data.comment}}`);
    document.getElementById('copy').textContent = 'Copied';
  }};
}});
load();
setInterval(() => load().catch(() => {{}}), 5000);
</script>
</body>
</html>"""
