from decimal import Decimal

import pytest

from app.billing import ton_pricing


def test_usd_conversion_uses_cached_ton_price(monkeypatch):
    monkeypatch.setattr(ton_pricing, "get_ton_usd_price", lambda: Decimal("2"))
    assert ton_pricing.usd_to_nano_ton(12) == 6_000_000_000
    assert ton_pricing.usd_to_nano_ton(29) == 14_500_000_000


def test_non_positive_usd_price_is_rejected(monkeypatch):
    monkeypatch.setattr(ton_pricing, "get_ton_usd_price", lambda: Decimal("2"))
    with pytest.raises(ton_pricing.TonPricingError):
        ton_pricing.usd_to_nano_ton(0)


def test_invalid_or_stale_provider_price_fails_closed(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"the-open-network": {"usd": 2, "last_updated_at": 1}}

    monkeypatch.setattr(ton_pricing.httpx, "get", lambda *args, **kwargs: Response())
    ton_pricing.reset_price_cache_for_tests()
    with pytest.raises(ton_pricing.TonPricingError, match="stale"):
        ton_pricing.get_ton_usd_price(force_refresh=True)
    ton_pricing.reset_price_cache_for_tests()
