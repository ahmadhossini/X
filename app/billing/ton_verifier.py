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


def _normalize_address(value: str | None) -> str:
    return (value or "").strip().casefold()


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


def _cursor_from_page(transactions: list[dict]) -> tuple[str, str] | None:
    if not transactions:
        return None
    oldest = transactions[-1]
    tx_id = oldest.get("transaction_id") or {}
    lt = str(tx_id.get("lt") or "").strip()
    tx_hash = str(tx_id.get("hash") or "").strip()
    if not lt or not tx_hash:
        return None
    return lt, tx_hash


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
    if not destination.strip():
        raise TonVerificationError("TON destination is not configured")
    if amount_nano_ton <= 0:
        raise TonVerificationError("TON amount must be positive")
    if not memo.strip():
        raise TonVerificationError("Payment memo is required")

    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    base_params = {
        "address": destination.strip(),
        "limit": "100",
        "archival": "true",
    }
    cursor: tuple[str, str] | None = None
    seen_cursors: set[tuple[str, str]] = set()

    async with httpx.AsyncClient(
        base_url="https://toncenter.com",
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers=headers,
    ) as client:
        for _ in range(10):
            params = dict(base_params)
            if cursor is not None:
                params["lt"], params["hash"] = cursor

            try:
                response = await client.get("/api/v2/getTransactions", params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise TonVerificationError(f"TON Center network error: {exc}") from exc
            except httpx.HTTPStatusError as exc:
                raise TonVerificationError(
                    f"TON Center HTTP error: {exc.response.status_code}"
                ) from exc
            except ValueError as exc:
                raise TonVerificationError("TON Center returned invalid JSON") from exc

            if not payload.get("ok", True):
                raise TonVerificationError("TON Center rejected the request")

            transactions = payload.get("result")
            if not isinstance(transactions, list):
                raise TonVerificationError("TON Center returned an invalid transaction list")

            for tx in transactions:
                if not isinstance(tx, dict):
                    continue

                tx_id = tx.get("transaction_id") or {}
                tx_hash = str(tx_id.get("hash") or tx.get("hash") or "").strip()
                if not tx_hash:
                    # Never confirm a payment without a blockchain transaction hash.
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

                if bool(message.get("bounced")):
                    continue

                destination_value = message.get("destination")
                if not isinstance(destination_value, str):
                    continue
                if _normalize_address(destination_value) != _normalize_address(destination):
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
                    source=message.get("source"),
                    memo=text,
                )

            next_cursor = _cursor_from_page(
                [item for item in transactions if isinstance(item, dict)]
            )
            if next_cursor is None or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    return None
