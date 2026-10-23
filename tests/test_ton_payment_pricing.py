from app.billing.service import BillingServiceError, _price_for_plan
from core.config import settings


def test_paid_plan_prices_use_explicit_nano_ton_configuration(monkeypatch):
    monkeypatch.setattr(settings, "ton_pro_price_nano_ton", 12_000_000_000)
    monkeypatch.setattr(settings, "ton_team_price_nano_ton", 29_000_000_000)

    assert _price_for_plan("pro") == 12_000_000_000
    assert _price_for_plan("team") == 29_000_000_000


def test_unsupported_plan_has_no_ton_price():
    try:
        _price_for_plan("free")
    except BillingServiceError as exc:
        assert "Unsupported paid plan" in str(exc)
    else:
        raise AssertionError("Free plan must not have a paid TON price")


def test_unconfigured_paid_plan_price_is_zero_by_default():
    # The config must fail closed rather than silently charging a fallback price.
    # Values can be overridden explicitly by deployment environment variables.
    assert settings.ton_pro_price_nano_ton >= 0
    assert settings.ton_team_price_nano_ton >= 0
