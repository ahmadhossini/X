from app.billing.stars import stars_amount_for_plan, validate_stars_precheckout
from app.billing.stars import StarsPaymentError


class Settings:
    stars_pro_amount = 600
    stars_team_amount = 1450


def test_stars_amounts_are_configured_for_paid_plans():
    assert stars_amount_for_plan("pro", Settings) == 600
    assert stars_amount_for_plan("team", Settings) == 1450


def test_free_plan_cannot_be_purchased_with_stars():
    try:
        stars_amount_for_plan("free", Settings)
    except StarsPaymentError as exc:
        assert "Unsupported paid plan" in str(exc)
    else:
        raise AssertionError("Free plan must not have a paid Stars amount")


def test_precheckout_requires_matching_user_currency_amount_and_pending_payment():
    class Payment:
        status = "pending"
        telegram_id = 123
        amount_stars = 600

    class DB:
        def scalar(self, query):
            return Payment()

    assert validate_stars_precheckout(DB(), "payload", 123, "XTR", 600)
    assert not validate_stars_precheckout(DB(), "payload", 999, "XTR", 600)
    assert not validate_stars_precheckout(DB(), "payload", 123, "TON", 600)
    assert not validate_stars_precheckout(DB(), "payload", 123, "XTR", 601)
