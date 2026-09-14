from datetime import datetime, timedelta, timezone

from billing.service import _sync_plan_state, _sync_total_credits
from database.models import UsageRecord, User


def test_subscription_expiry_preserves_topup_credits():
    user = User(
        telegram_id=1,
        plan="pro",
        credits=120,
        subscription_credits=100,
        topup_credits=20,
        credits_reset_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    _sync_plan_state(user, datetime.now(timezone.utc))

    assert user.plan == "free"
    assert user.subscription_credits == 0
    assert user.topup_credits == 20
    assert user.credits == 20


def test_total_balance_is_derived_from_separate_sources():
    user = User(
        telegram_id=2,
        plan="pro",
        credits=999,
        subscription_credits=7,
        topup_credits=13,
    )

    _sync_total_credits(user)

    assert user.credits == 20


def test_usage_record_can_track_reserved_credit_sources():
    usage = UsageRecord(
        task_id="task-1",
        user_id=1,
        repository="owner/repo",
        request="fix bug",
        credits_reserved=10,
        credits_used=0,
        subscription_credits_reserved=6,
        topup_credits_reserved=4,
        status="reserved",
    )

    assert usage.subscription_credits_reserved + usage.topup_credits_reserved == usage.credits_reserved
