from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import billing.service as billing
import bot.task_queue as task_queue
from database.models import Base, GitHubInstallation, Task, UsageRecord, User


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(billing, "SessionLocal", Session)
    monkeypatch.setattr(task_queue, "SessionLocal", Session)

    with Session() as session:
        # Use a paid-plan fixture so the lifecycle tests can control the
        # starting balance directly. Free users intentionally reset to their
        # daily allowance before a reservation.
        user = User(telegram_id=12345, language="fa", plan="pro", credits=20, credits_reset_at=datetime.now(timezone.utc) + timedelta(days=1))
        session.add(user)
        session.flush()
        installation = GitHubInstallation(
            user_id=user.id,
            installation_id=153037631,
            github_user_id=290021265,
            github_login="goodahmad001o-lang",
            active=True,
        )
        session.add(installation)
        session.commit()

    yield Session
    engine.dispose()


def _create_reserved_task(Session, *, credits=5):
    reservation = billing.reserve_task_credits(
        12345,
        "goodahmad001o-lang/X",
        "add a test",
        credits,
        installation_id=153037631,
        model="gemini-test",
        chat_id=9876,
        language="fa",
    )
    with Session() as session:
        task = session.get(Task, reservation.task_id)
        usage = session.scalar(select(UsageRecord).where(UsageRecord.task_id == reservation.task_id))
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        return reservation, task, usage, user


def test_reservation_persists_task_and_usage_metadata(db):
    reservation, task, usage, user = _create_reserved_task(db, credits=5)

    assert reservation.remaining == 15
    assert task is not None
    assert task.status == "queued"
    assert task.installation_id == 153037631
    assert task.chat_id == 9876
    assert task.language == "fa"
    assert usage is not None
    assert usage.status == "reserved"
    assert usage.credits_reserved == 5
    assert usage.credits_used == 0
    assert user.credits == 15


def test_second_active_task_is_rejected_without_changing_balance(db):
    first, _, _, _ = _create_reserved_task(db, credits=5)

    with pytest.raises(billing.BillingError, match="Active task already exists"):
        billing.reserve_task_credits(
            12345,
            "goodahmad001o-lang/X",
            "make another change",
            5,
            installation_id=153037631,
            model="gemini-test",
            chat_id=9876,
            language="fa",
        )

    with db() as session:
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        assert user.credits == 15
        assert session.scalar(select(Task.id).where(Task.id == first.task_id)) == first.task_id
        assert len(session.scalars(select(Task)).all()) == 1


def test_insufficient_credits_creates_no_task_or_usage(db):
    with db() as session:
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        user.credits = 2
        session.commit()

    with pytest.raises(billing.BillingError, match="Insufficient credits"):
        billing.reserve_task_credits(
            12345,
            "goodahmad001o-lang/X",
            "add a change",
            5,
            installation_id=153037631,
            model="gemini-test",
            chat_id=9876,
            language="fa",
        )

    with db() as session:
        assert session.scalar(select(Task.id)) is None
        assert session.scalar(select(UsageRecord.id)) is None
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        assert user.credits == 2


def test_claim_task_moves_queued_task_to_running(db):
    reservation, _, _, _ = _create_reserved_task(db)

    claimed = task_queue.claim_task("test-worker")

    assert claimed is not None
    assert claimed.id == reservation.task_id
    assert claimed.status == "running"
    assert claimed.worker_id == "test-worker"
    assert claimed.locked_at is not None

    assert task_queue.claim_task("second-worker") is None


def test_transition_complete_and_fail_are_state_safe_and_idempotent(db):
    reservation, _, _, _ = _create_reserved_task(db)

    assert billing.transition_task(reservation.task_id, "queued", "running") is True
    assert billing.transition_task(reservation.task_id, "queued", "planning") is False
    assert billing.transition_task(reservation.task_id, "running", "planning") is True
    assert billing.transition_task(
        reservation.task_id,
        "planning",
        "branch_created",
        branch="xai/task-test",
    ) is True
    assert billing.transition_task(
        reservation.task_id,
        "branch_created",
        "committed",
        commit_sha="abc123",
    ) is True
    assert billing.transition_task(
        reservation.task_id,
        "committed",
        "pr_created",
        pull_request_number=42,
    ) is True

    billing.complete_task(reservation.task_id, "gemini-test")
    billing.complete_task(reservation.task_id, "gemini-test")

    with db() as session:
        task = session.get(Task, reservation.task_id)
        usage = session.scalar(select(UsageRecord).where(UsageRecord.task_id == reservation.task_id))
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        assert task.status == "completed"
        assert usage.status == "completed"
        assert usage.credits_used == 4
        assert user.credits == 15

    # A failed cleanup after successful completion must not refund credits.
    billing.fail_task(reservation.task_id, "gemini-test", "late_worker_error", refund=True)
    with db() as session:
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        usage = session.scalar(select(UsageRecord).where(UsageRecord.task_id == reservation.task_id))
        assert user.credits == 15
        assert usage.status == "completed"


def test_failed_task_refunds_reserved_credits_once(db):
    reservation, _, _, _ = _create_reserved_task(db, credits=5)

    billing.fail_task(reservation.task_id, "gemini-test", "worker_error", refund=True)
    billing.fail_task(reservation.task_id, "gemini-test", "worker_error_again", refund=True)

    with db() as session:
        user = session.scalar(select(User).where(User.telegram_id == 12345))
        task = session.get(Task, reservation.task_id)
        usage = session.scalar(select(UsageRecord).where(UsageRecord.task_id == reservation.task_id))
        assert user.credits == 20
        assert task.status == "failed"
        assert task.error == "worker_error"
        assert usage.status == "refunded"
        assert usage.credits_used == 0
