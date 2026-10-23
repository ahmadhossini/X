from types import SimpleNamespace

from app.billing import service as billing_service
from app.billing.service import BillingServiceError, _price_for_plan


def test_paid_plan_prices_use_usd_plan_price_and_dynamic_rate(monkeypatch):
    requested = []
    def fake_price(plan_key, price_usd):
        requested.append((plan_key, price_usd))
        return {"pro": 4_000_000_000, "team": 9_000_000_000}[plan_key]

    monkeypatch.setattr(billing_service, "get_plan_price_nano_ton", fake_price)

    assert _price_for_plan("pro") == 4_000_000_000
    assert _price_for_plan("team") == 9_000_000_000
    assert requested == [("pro", 12), ("team", 29)]


def test_unsupported_plan_has_no_ton_price():
    try:
        _price_for_plan("free")
    except BillingServiceError as exc:
        assert "Unsupported paid plan" in str(exc)
    else:
        raise AssertionError("Free plan must not have a paid TON price")
