from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import billing.payments as payments
from billing.payments import activate_paid_plan, activate_topup
from database.models import Payment, Subscription, User
from database.session import Base


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_paid_plan_activation_is_idempotent(monkeypatch):
    engine, session_local = _session_factory()
    monkeypatch.setattr(payments, "SessionLocal", session_local)

    try:
        with session_local() as db:
            db.add(User(telegram_id=1001, credits=0, subscription_credits=0, topup_credits=0))
            db.commit()

        first = activate_paid_plan(
            1001,
            "starter",
            "ton",
            "payment-plan-1",
            999,
            asset="USDT",
        )
        second = activate_paid_plan(
            1001,
            "starter",
            "ton",
            "payment-plan-1",
            999,
            asset="USDT",
        )

        assert first is True
        assert second is False

        with session_local() as db:
            user = db.scalar(select(User).where(User.telegram_id == 1001))
            assert user.subscription_credits == 50
            assert user.topup_credits == 0
            assert user.credits == 50
            assert db.scalar(select(func.count()).select_from(Payment)) == 1
            assert db.scalar(select(func.count()).select_from(Subscription)) == 1
            payment = db.scalar(select(Payment))
            assert payment.status == "paid"
            assert payment.provider_payment_id == "payment-plan-1"
    finally:
        engine.dispose()


def test_topup_activation_is_idempotent(monkeypatch):
    engine, session_local = _session_factory()
    monkeypatch.setattr(payments, "SessionLocal", session_local)

    try:
        with session_local() as db:
            db.add(User(telegram_id=1002, credits=0, subscription_credits=0, topup_credits=0))
            db.commit()

        first = activate_topup(
            1002,
            "topup",
            "ton",
            "payment-topup-1",
            499,
            asset="USDT",
        )
        second = activate_topup(
            1002,
            "topup",
            "ton",
            "payment-topup-1",
            499,
            asset="USDT",
        )

        assert first is True
        assert second is False

        with session_local() as db:
            user = db.scalar(select(User).where(User.telegram_id == 1002))
            assert user.subscription_credits == 0
            assert user.topup_credits == 20
            assert user.credits == 20
            assert db.scalar(select(func.count()).select_from(Payment)) == 1
            assert db.scalar(select(func.count()).select_from(Subscription)) == 0
    finally:
        engine.dispose()
