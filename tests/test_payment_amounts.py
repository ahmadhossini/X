from billing.payments import _validate_payment_amount
from billing.plans import get_plan


def test_payment_amount_uses_exact_plan_price_in_cents():
    assert _validate_payment_amount(get_plan("starter"), 999) == 999
    assert _validate_payment_amount(get_plan("pro"), 2999) == 2999
    assert _validate_payment_amount(get_plan("topup"), 499) == 499


def test_payment_amount_rejects_mismatched_price():
    try:
        _validate_payment_amount(get_plan("starter"), 900)
    except ValueError as exc:
        assert str(exc) == "Payment amount does not match plan price"
    else:
        raise AssertionError("Expected mismatched payment amount to be rejected")


def test_payment_amount_rejects_non_numeric_values():
    try:
        _validate_payment_amount(get_plan("starter"), "nine dollars")
    except ValueError as exc:
        assert str(exc) == "Invalid payment amount"
    else:
        raise AssertionError("Expected invalid payment amount to be rejected")
