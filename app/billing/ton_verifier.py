from __future__ import annotations

import asyncio
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
    return re.sub(r"\s+", "", value or "").lower()


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


async def _get_transactions(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    destination: str,
    *,
    start_lt: int | None,
    start_hash: str | None,
) -> dict:
    params: dict[str, str] = {
        "address": destination,
        "limit": "100",
        "archival": "true",
    }
    if start_lt is not None and start_hash:
        params["lt"] = str(start_lt)
        params["hash"] = start_hash

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get("/api/v2/getTransactions", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("ok", True):
                raise TonVerificationError("TON Center rejected the transaction query")
            return payload
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt == 2:
                break
            await asyncio.sleep(min(2 ** attempt, 4))

    raise TonVerificationError(f"TON Center request failed: {last_error}") from last_error


async def find_payment_transfer(
    *,
    destination: str,
    amount_nano_ton: int,
    memo: str,
    after_lt: int | None = None,
) -> VerifiedTonTransfer | None:
    if not destination.strip():
        raise TonVerificationError("TON destination is not configured")
    if amount_nano_ton <= 0:
        raise TonVerificationError("Invalid TON payment amount")
    if not memo.strip():
        raise TonVerificationError("Invalid TON payment memo")

    api_key = settings.toncenter_api_key
    if not api_key:
        raise TonVerificationError("TONCENTER_API_KEY is not configured")
    if settings.ton_network != "mainnet":
        raise TonVerificationError("TON payment verification requires TON_NETWORK=mainnet")

    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
    }

    # TON Center v2 getTransactions paginates with previous_transaction.lt/hash.
    # Walk a bounded number of pages so an old legitimate payment is not missed
    # while still protecting the API from an unbounded scan.
    cursor_lt = after_lt
    cursor_hash: str | None = None
    max_pages = 10

    async with httpx.AsyncClient(
        base_url="https://toncenter.com",
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        for _ in range(max_pages):
            payload = await _get_transactions(
                client,
                headers,
                destination,
                start_lt=cursor_lt,
                start_hash=cursor_hash,
            )

            result = payload.get("result")
            if not isinstance(result, list):
                raise TonVerificationError("TON Center returned an invalid transaction list")

            for tx in result:
                if not isinstance(tx, dict):
                    continue

                tx_id = tx.get("transaction_id") or {}
                tx_hash = str(tx_id.get("hash") or tx.get("hash") or "").strip()
                if not tx_hash:
                    continue

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

                message_destination = message.get("destination")
                if (
                    message_destination
                    and _norm(str(message_destination)) != _norm(destination)
                ):
                    continue

                amount = _amount_from_message(message)
                if amount != amount_nano_ton:
                    continue

                text = _extract_text(message)
                if text != memo:
                    continue

                return VerifiedTonTransfer(
                    tx_hash=tx_hash,
                    amount_nano_ton=amount,
                    source=(
                        str(message.get("source"))
                        if message.get("source") is not None
                        else None
                    ),
                    memo=text,
                )

            previous = payload.get("previous_transaction")
            if not isinstance(previous, dict):
                break

            next_lt = previous.get("lt")
            next_hash = previous.get("hash")
            if next_lt is None or not next_hash:
                break

            try:
                next_lt_int = int(next_lt)
            except (TypeError, ValueError):
                break

            # Prevent a broken provider response from looping forever.
            if cursor_lt is not None and next_lt_int >= cursor_lt:
                break

            cursor_lt = next_lt_int
            cursor_hash = str(next_hash)

    return None
