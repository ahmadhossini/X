from decimal import Decimal

from billing.plans import PLANS, get_plan
from billing.ton import DEFAULT_USDT_MASTER, USDT_DECIMALS, _amount_units, _deep_link


def test_plan_prices_and_credit_packages_are_stable():
    assert PLANS["starter"].price_usd == Decimal("9.99")
    assert PLANS["starter"].credits == 50
    assert PLANS["pro"].price_usd == Decimal("29.99")
    assert PLANS["pro"].credits == 200
    assert PLANS["team"].price_usd == Decimal("79.99")
    assert PLANS["team"].credits == 600
    assert PLANS["topup"].subscription is False
    assert PLANS["topup"].credits == 20


def test_ton_usdt_amount_uses_six_decimals():
    assert USDT_DECIMALS == 6
    assert _amount_units("starter") == 9_990_000
    assert _amount_units("pro") == 29_990_000
    assert _amount_units("team") == 79_990_000
    assert _amount_units("topup") == 4_990_000


def test_ton_deep_link_contains_exact_jetton_amount_and_comment():
    link = _deep_link("UQExample", 9_990_000, "XAI-ABC123")
    assert link.startswith("ton://transfer/UQExample?")
    assert f"jetton={DEFAULT_USDT_MASTER}" in link
    assert "amount=9990000" in link
    assert "text=XAI-ABC123" in link


def test_unknown_plan_is_rejected():
    try:
        get_plan("does-not-exist")
    except ValueError as exc:
        assert str(exc) == "Unknown plan"
    else:
        raise AssertionError("unknown plan was accepted")
