import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from billing import payments, ton
from database.models import Base, Payment, Subscription, User


def _setup_ton_order(monkeypatch, *, created_at=None, amount_units=9_990_000, comment="XAI-E2ETEST1234"):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(ton, "SessionLocal", TestSession)
    monkeypatch.setattr(payments, "SessionLocal", TestSession)
    monkeypatch.setattr(ton.settings, "ton_payment_address", "EQTEST-RECEIVER")
    monkeypatch.setattr(ton.settings, "ton_usdt_master_address", "EQTEST-USDT")
    monkeypatch.setattr(ton.settings, "ton_payment_expiry_minutes", 30)

    telegram_id = 987654321
    order_id = "ton-e2e-test"
    created_at = created_at or int(datetime.now(timezone.utc).timestamp())

    with TestSession() as db:
        user = User(
            telegram_id=telegram_id,
            plan="free",
            credits=0,
            subscription_credits=0,
            topup_credits=0,
        )
        db.add(user)
        db.flush()
        db.add(
            Payment(
                user_id=user.id,
                provider="ton_direct",
                provider_payment_id=order_id,
                plan="starter",
                amount_usd=9,
                amount_usd_cents=999,
                asset="USDT",
                status="pending",
                raw_payload=json.dumps(
                    {
                        "order_id": order_id,
                        "comment": comment,
                        "address": "EQTEST-RECEIVER",
                        "amount_units": amount_units,
                        "created_at": created_at,
                    }
                ),
            )
        )
        db.commit()

    return TestSession, telegram_id, order_id, created_at, amount_units, comment


def _assert_not_activated(TestSession, order_id, telegram_id):
    with TestSession() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        payment = db.scalar(
            select(Payment).where(Payment.provider_payment_id == order_id)
        )
        subscriptions = db.scalars(
            select(Subscription).where(Subscription.payment_id == order_id)
        ).all()

        assert payment.status == "pending"
        assert user.plan == "free"
        assert user.subscription_credits == 0
        assert user.topup_credits == 0
        assert user.credits == 0
        assert subscriptions == []


def test_verify_usdt_order_activates_credits_end_to_end(monkeypatch):
    TestSession, telegram_id, order_id, created_at, amount_units, comment = _setup_ton_order(monkeypatch)

    transfer = {
        "transaction_aborted": False,
        "destination": "EQTEST-RECEIVER",
        "jetton_master": "EQTEST-USDT",
        "transaction_hash": "abc123",
        "utime": created_at,
        "amount": str(amount_units),
        "decoded_forward_payload": {"text": comment},
    }
    calls = []

    def fake_find_matching_transfer(created, amount, expected_comment):
        calls.append((created, amount, expected_comment))
        return transfer

    monkeypatch.setattr(ton, "_find_matching_transfer", fake_find_matching_transfer)

    result = ton.verify_usdt_order(order_id)

    assert result["status"] == "paid"
    assert result["order_id"] == order_id
    assert result["transaction_hash"] == "abc123"
    assert calls == [(created_at, amount_units, comment)]

    with TestSession() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        payment = db.scalar(
            select(Payment).where(Payment.provider_payment_id == order_id)
        )
        subscription = db.scalar(
            select(Subscription).where(Subscription.payment_id == order_id)
        )

        assert payment.status == "paid"
        assert user.plan == "starter"
        assert user.subscription_credits == 50
        assert user.topup_credits == 0
        assert user.credits == 50
        assert subscription is not None
        assert subscription.credits_granted == 50
        assert subscription.payment_method == "ton_direct"

    # A second verification must not call TON Center again or grant credits twice.
    result_again = ton.verify_usdt_order(order_id)
    assert result_again["status"] == "paid"
    assert len(calls) == 1

    with TestSession() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        subscriptions = db.scalars(
            select(Subscription).where(Subscription.payment_id == order_id)
        ).all()
        assert user.subscription_credits == 50
        assert user.credits == 50
        assert len(subscriptions) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda transfer: transfer.update(amount="9990000"), id="wrong-amount"),
        pytest.param(
            lambda transfer: transfer.update(decoded_forward_payload={"text": "XAI-WRONG"}),
            id="wrong-comment",
        ),
        pytest.param(
            lambda transfer: transfer.update(destination="EQWRONG-RECEIVER"),
            id="wrong-destination",
        ),
        pytest.param(
            lambda transfer: transfer.update(jetton_master="EQWRONG-USDT"),
            id="wrong-jetton-master",
        ),
        pytest.param(lambda transfer: transfer.update(transaction_aborted=True), id="aborted"),
        pytest.param(lambda transfer: transfer.update(transaction_hash=""), id="missing-transaction-hash"),
    ],
)
def test_verify_usdt_order_rejects_invalid_transfer(monkeypatch, mutation):
    TestSession, telegram_id, order_id, created_at, amount_units, comment = _setup_ton_order(monkeypatch)

    transfer = {
        "transaction_aborted": False,
        "destination": "EQTEST-RECEIVER",
        "jetton_master": "EQTEST-USDT",
        "transaction_hash": "abc123",
        "utime": created_at,
        "amount": str(amount_units),
        "decoded_forward_payload": {"text": comment},
    }
    mutation(transfer)
    monkeypatch.setattr(ton, "_find_matching_transfer", lambda *_args: None)

    result = ton.verify_usdt_order(order_id)

    assert result == {"status": "pending", "order_id": order_id}
    _assert_not_activated(TestSession, order_id, telegram_id)


def test_verify_usdt_order_rejects_transfer_outside_time_window(monkeypatch):
    TestSession, telegram_id, order_id, created_at, amount_units, comment = _setup_ton_order(monkeypatch)

    transfer = {
        "transaction_aborted": False,
        "destination": "EQTEST-RECEIVER",
        "jetton_master": "EQTEST-USDT",
        "transaction_hash": "abc123",
        "utime": created_at + 31 * 60,
        "amount": str(amount_units),
        "decoded_forward_payload": {"text": comment},
    }
    monkeypatch.setattr(ton, "_find_matching_transfer", lambda *_args: None)

    result = ton.verify_usdt_order(order_id)

    assert result == {"status": "pending", "order_id": order_id}
    _assert_not_activated(TestSession, order_id, telegram_id)


def test_verify_usdt_order_expires_without_checking_transfer(monkeypatch):
    expired_created_at = int(datetime.now(timezone.utc).timestamp()) - (31 * 60)
    TestSession, telegram_id, order_id, *_ = _setup_ton_order(
        monkeypatch, created_at=expired_created_at
    )

    calls = []

    def should_not_search(*_args):
        calls.append(True)
        return None

    monkeypatch.setattr(ton, "_find_matching_transfer", should_not_search)

    result = ton.verify_usdt_order(order_id)

    assert result == {"status": "expired", "order_id": order_id}
    assert calls == []

    with TestSession() as db:
        payment = db.scalar(
            select(Payment).where(Payment.provider_payment_id == order_id)
        )
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert payment.status == "expired"
        assert user.credits == 0
        assert user.subscription_credits == 0
        assert user.topup_credits == 0
