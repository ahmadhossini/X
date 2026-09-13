from __future__ import annotations

import base64
import binascii
import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx
from sqlalchemy import select

from billing.payments import activate_paid_plan
from billing.plans import get_plan
from core.config import settings
from database.models import Payment
from database.session import SessionLocal

TONCENTER_BASE_URL = "https://toncenter.com/api/v3"
USDT_DECIMALS = 6
DEFAULT_USDT_MASTER = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"


class TonPaymentError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if settings.toncenter_api_key:
        return {"X-API-Key": settings.toncenter_api_key}
    return {}


def _usdt_master() -> str:
    return settings.ton_usdt_master_address or DEFAULT_USDT_MASTER


def _amount_units(plan_key: str) -> int:
    plan = get_plan(plan_key)
    return int(plan.price_usd * Decimal(10**USDT_DECIMALS))


def _new_order_id() -> str:
    return f"ton-{uuid.uuid4().hex}"


def _new_comment() -> str:
    return f"XAI-{uuid.uuid4().hex[:12].upper()}"


def create_usdt_order(telegram_id: int, plan_key: str) -> dict:
    plan = get_plan(plan_key)
    address = settings.ton_payment_address.strip()
    if not address:
        raise TonPaymentError("TON_PAYMENT_ADDRESS is not configured")

    order_id = _new_order_id()
    comment = _new_comment()
    amount_units = _amount_units(plan_key)
    now = datetime.now(timezone.utc)
    payload = {
        "order_id": order_id,
        "comment": comment,
        "address": address,
        "asset": "USDT",
        "network": "TON",
        "amount_units": amount_units,
        "created_at": int(now.timestamp()),
    }

    with SessionLocal() as db:
        db.add(
            Payment(
                user_id=_user_id(db, telegram_id),
                provider="ton_direct",
                provider_payment_id=order_id,
                plan=plan.key,
                amount_usd=int(plan.price_usd),
                amount_usd_cents=plan.price_usd_cents,
                asset="USDT",
                status="pending",
                raw_payload=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.commit()

    deep_link = (
        f"ton://transfer/{quote(address, safe='') }"
        f"?jetton={quote(_usdt_master(), safe='')}&amount={amount_units}&text={quote(comment, safe='')}"
    )
    return {
        "order_id": order_id,
        "plan": plan.key,
        "title": plan.title,
        "amount_usdt": f"{plan.price_usd:.2f}",
        "amount_units": amount_units,
        "asset": "USDT",
        "network": "TON",
        "address": address,
        "comment": comment,
        "deep_link": deep_link,
        "checkout_url": f"{settings.public_base_url}/api/payments/ton/checkout/{order_id}",
        "expires_in": settings.ton_payment_expiry_minutes * 60,
    }


def _user_id(db, telegram_id: int) -> int:
    from database.models import User

    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise TonPaymentError("User not found")
    return user.id


def _extract_text(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "comment", "value"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        for candidate in value.values():
            found = _extract_text(candidate)
            if found:
                return found
    if isinstance(value, list):
        if value and all(isinstance(item, int) and 0 <= item <= 255 for item in value):
            raw = bytes(value)
            for prefix in (b"\x00\x00\x00\x00", b"\xff"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]
                    break
            try:
                return raw.decode("utf-8").strip("\x00") or None
            except UnicodeDecodeError:
                pass
        for candidate in value:
            found = _extract_text(candidate)
            if found:
                return found
    return None


def _decode_payload_string(value: str) -> str | None:
    for decoder in (base64.urlsafe_b64decode, bytes.fromhex):
        try:
            raw = decoder(value + ("=" * (-len(value) % 4)) if decoder is base64.urlsafe_b64decode else value)
        except (ValueError, binascii.Error, TypeError):
            continue
        for prefix in (b"\x00\x00\x00\x00", b"\xff"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        try:
            text = raw.decode("utf-8").strip("\x00")
            if text:
                return text
        except UnicodeDecodeError:
            continue
    return None


def _transfer_comment(transfer: dict) -> str | None:
    for key in ("decoded_forward_payload", "decoded_custom_payload"):
        found = _extract_text(transfer.get(key))
        if found:
            return found
    raw = transfer.get("forward_payload")
    if isinstance(raw, str):
        return _decode_payload_string(raw)
    return None


def _find_matching_transfer(order: Payment, created_at: int, amount_units: int, comment: str) -> dict | None:
    params = {
        "owner_address": settings.ton_payment_address,
        "direction": "in",
        "jetton_master": _usdt_master(),
        "start_utime": max(0, created_at - 120),
        "limit": 100,
        "sort": "desc",
    }
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{TONCENTER_BASE_URL}/jetton/transfers",
            headers=_headers(),
            params=params,
        )
    response.raise_for_status()
    data = response.json()
    transfers = data.get("jetton_transfers") or []
    for transfer in transfers:
        if transfer.get("transaction_aborted"):
            continue
        if str(transfer.get("amount")) != str(amount_units):
            continue
        if _transfer_comment(transfer) != comment:
            continue
        return transfer
    return None


def verify_usdt_order(order_id: str) -> dict:
    with SessionLocal() as db:
        order = db.scalar(
            select(Payment).where(
                Payment.provider == "ton_direct",
                Payment.provider_payment_id == order_id,
            ).with_for_update()
        )
        if not order:
            raise TonPaymentError("Payment order not found")
        if order.status == "paid":
            return {"status": "paid", "order_id": order_id}
        if order.status != "pending":
            return {"status": order.status, "order_id": order_id}

        raw = json.loads(order.raw_payload or "{}")
        created_at = int(raw.get("created_at") or int(order.created_at.replace(tzinfo=timezone.utc).timestamp()))
        if int(time.time()) - created_at > settings.ton_payment_expiry_minutes * 60:
            order.status = "expired"
            db.commit()
            return {"status": "expired", "order_id": order_id}
        comment = str(raw.get("comment") or "")
        amount_units = int(raw.get("amount_units") or 0)

    transfer = _find_matching_transfer(order, created_at, amount_units, comment)
    if not transfer:
        return {"status": "pending", "order_id": order_id}

    activated = activate_paid_plan(
        telegram_id=_telegram_id_for_order(order_id),
        plan_key=order.plan,
        payment_method="ton_direct",
        payment_id=order_id,
        amount_usd_cents=order.amount_usd_cents or order.amount_usd * 100,
        asset="USDT",
        raw_payload=transfer,
    )
    return {
        "status": "paid" if activated or _payment_is_paid(order_id) else "pending",
        "order_id": order_id,
        "transaction_hash": transfer.get("transaction_hash"),
    }


def _telegram_id_for_order(order_id: str) -> int:
    with SessionLocal() as db:
        from database.models import User

        row = db.scalar(
            select(User.telegram_id)
            .join(Payment, Payment.user_id == User.id)
            .where(Payment.provider == "ton_direct", Payment.provider_payment_id == order_id)
        )
        if row is None:
            raise TonPaymentError("Order owner not found")
        return int(row)


def _payment_is_paid(order_id: str) -> bool:
    with SessionLocal() as db:
        row = db.scalar(
            select(Payment.status).where(
                Payment.provider == "ton_direct",
                Payment.provider_payment_id == order_id,
            )
        )
        return row == "paid"
