from __future__ import annotations

import os
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import httpx


COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
PRICE_CACHE_TTL_SECONDS = 300
MAX_PRICE_AGE_SECONDS = 600
_REQUEST_TIMEOUT_SECONDS = 5.0
_cache_lock = threading.Lock()
_cached_price_usd: Decimal | None = None
_cached_fetched_at = 0.0


class TonPricingError(RuntimeError):
    """Raised when a trustworthy current TON/USD price is unavailable."""


def get_ton_usd_price(*, force_refresh: bool = False) -> Decimal:
    """Return a cached TON/USD market price, refreshing at most every five minutes."""
    global _cached_price_usd, _cached_fetched_at

    now = time.monotonic()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_price_usd is not None
            and now - _cached_fetched_at < PRICE_CACHE_TTL_SECONDS
        ):
            return _cached_price_usd

        headers = {}
        api_key = os.getenv("COINGECKO_API_KEY", "").strip()
        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        try:
            response = httpx.get(
                COINGECKO_SIMPLE_PRICE_URL,
                params={
                    "ids": "the-open-network",
                    "vs_currencies": "usd",
                    "include_last_updated_at": "true",
                },
                headers=headers,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            ton_data = payload.get("the-open-network")
            raw_price = ton_data.get("usd") if isinstance(ton_data, dict) else None
            price = Decimal(str(raw_price))
            updated_at = int(ton_data.get("last_updated_at", 0))
            if not price.is_finite() or price <= 0:
                raise TonPricingError("TON/USD provider returned an invalid price")
            if updated_at <= 0 or abs(time.time() - updated_at) > MAX_PRICE_AGE_SECONDS:
                raise TonPricingError("TON/USD provider returned stale price data")
        except TonPricingError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, InvalidOperation) as exc:
            raise TonPricingError("Current TON/USD price is temporarily unavailable") from exc

        _cached_price_usd = price
        _cached_fetched_at = time.monotonic()
        return price


def usd_to_nano_ton(price_usd: int | Decimal) -> int:
    """Convert a USD plan price into nanoTON using the current cached market rate."""
    try:
        usd = Decimal(str(price_usd))
    except (InvalidOperation, ValueError) as exc:
        raise TonPricingError("Invalid USD plan price") from exc
    if not usd.is_finite() or usd <= 0:
        raise TonPricingError("USD plan price must be positive")
    ton_usd = get_ton_usd_price()
    nano_ton = (usd / ton_usd * Decimal(1_000_000_000)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    amount = int(nano_ton)
    if amount <= 0:
        raise TonPricingError("Calculated TON amount is invalid")
    return amount


def get_plan_price_nano_ton(plan_key: str, price_usd: int) -> int:
    if plan_key not in {"pro", "team"}:
        raise TonPricingError(f"Unsupported paid plan: {plan_key}")
    return usd_to_nano_ton(price_usd)


def reset_price_cache_for_tests() -> None:
    """Clear process-local cache; intended for deterministic unit tests."""
    global _cached_price_usd, _cached_fetched_at
    with _cache_lock:
        _cached_price_usd = None
        _cached_fetched_at = 0.0
