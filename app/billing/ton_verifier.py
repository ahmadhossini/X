from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from core.config import settings


class TonVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedTonTransfer:
    tx_hash: str
    amount_nano_ton: int
    source: str | None
    memo: str | None


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value or "").lower()


def _extract_text(message: object) -> str:
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, dict):
        for key in ("message", "text", "comment"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("msg_data", "body", "message_content", "content"):
            value = message.get(key)
            text = _extract_text(value)
            if text:
                return text
    return ""


def _transaction_message(tx: dict) -> dict:
    for key in ("in_msg", "in_msg_full", "in_message"):
        value = tx.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _amount_from_message(message: dict) -> int:
    value = message.get("value")
    if isinstance(value, dict):
        value = value.get("grams") or value.get("amount")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def find_payment_transfer(
    *,
    destination: str,
    amount_nano_ton: int,
    memo: str,
    after_lt: int | None = None,
) -> VerifiedTonTransfer | None:
    api_key = settings.toncenter_api_key
    if not api_key:
        raise TonVerificationError("TONCENTER_API_KEY is not configured")
    if settings.ton_network != "mainnet":
        raise TonVerificationError("TON payment verification requires TON_NETWORK=mainnet")

    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    params = {"address": destination, "limit": "100", "archival": "true"}

    async with httpx.AsyncClient(
        base_url="https://toncenter.com",
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers=headers,
    ) as client:
        response = await client.get("/api/v2/getTransactions", params=params)
        response.raise_for_status()
        payload = response.json()

    if not payload.get("ok", True):
        raise TonVerificationError("TON Center rejected the request")

    for tx in payload.get("result", []):
        tx_id = tx.get("transaction_id") or {}
        tx_hash = str(tx_id.get("hash") or tx.get("hash") or "").strip()
        lt_raw = tx_id.get("lt") or tx.get("lt")
        try:
            lt = int(lt_raw) if lt_raw is not None else None
        except (TypeError, ValueError):
            lt = None
        if after_lt is not None and lt is not None and lt <= after_lt:
            continue

        message = _transaction_message(tx)
        if not message:
            continue
        if message.get("destination") and _norm(message.get("destination")) != _norm(destination):
            continue

        amount = _amount_from_message(message)
        if amount < amount_nano_ton:
            continue

        text = _extract_text(message)
        if text != memo:
            continue

        return VerifiedTonTransfer(
            tx_hash=tx_hash,
            amount_nano_ton=amount,
            source=message.get("source"),
            memo=text,
        )

    return None
