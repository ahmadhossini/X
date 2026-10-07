from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.billing.plans import PLANS
from core.config import settings
from database.models import GitHubInstallation, Task, UsageRecord, User
from database.session import SessionLocal


class BillingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskReservation:
    task_id: str
    remaining: int


def _monthly_credits(plan: str) -> int:
    if plan == "free":
        return settings.free_monthly_credits
    if plan == "pro":
        return settings.pro_monthly_credits
    if plan == "team":
        return settings.team_monthly_credits
    return PLANS["free"].monthly_credits


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def ensure_user_credit_state(telegram_id: int) -> tuple[int, str]:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if user is None:
            raise BillingError("User not found")

        now = datetime.now(timezone.utc)
        plan = user.plan if user.plan in PLANS else "free"
        if user.plan != plan:
            user.plan = plan

        credits_reset_at = _as_utc(user.credits_reset_at)
        if credits_reset_at is None or credits_reset_at <= now:
            user.credits = _monthly_credits(plan)
            user.credits_reset_at = now + timedelta(days=30)
            db.commit()

        return user.credits, plan


def estimate_task_credits(request: str) -> int:
    text = (request or "").lower()
    heavy_terms = ("bug", "debug", "error", "fix", "باگ", "خطا", "اشتباه", "رفع")
    return 10 if any(term in text for term in heavy_terms) else 5


def reserve_task_credits(
    telegram_id: int,
    repository: str,
    request: str,
    credits: int,
    *,
    installation_id: int | None = None,
    model: str,
    chat_id: int | None = None,
    language: str = "en",
) -> TaskReservation:
    if credits <= 0:
        raise BillingError("Invalid credit amount")

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.telegram_id == telegram_id).with_for_update()
        )
        if user is None:
            raise BillingError("User not found")

        now = datetime.now(timezone.utc)
        plan = user.plan if user.plan in PLANS else "free"
        credits_reset_at = _as_utc(user.credits_reset_at)
        if credits_reset_at is None or credits_reset_at <= now:
            user.credits = _monthly_credits(plan)
            user.credits_reset_at = now + timedelta(days=30)

        installation_query = (
            select(GitHubInstallation)
            .where(
                GitHubInstallation.user_id == user.id,
                GitHubInstallation.active.is_(True),
            )
            .order_by(GitHubInstallation.updated_at.desc())
        )
        installation = db.scalar(installation_query)
        if installation is None:
            raise BillingError("GitHub not connected")
        if installation_id is not None and installation.installation_id != installation_id:
            owned = db.scalar(
                select(GitHubInstallation).where(
                    GitHubInstallation.user_id == user.id,
                    GitHubInstallation.installation_id == installation_id,
                    GitHubInstallation.active.is_(True),
                )
            )
            if owned is None:
                raise BillingError("GitHub not connected")
            installation = owned

        active = db.scalar(
            select(Task).where(
                Task.user_id == user.id,
                Task.status.in_(
                    (
                        "queued",
                        "running",
                        "planning",
                        "branch_created",
                        "changes_applied",
                        "committed",
                        "pr_created",
                    )
                ),
            )
        )
        if active is not None:
            raise BillingError("Active task already exists")

        if user.credits < credits:
            raise BillingError("Insufficient credits")

        task_id = uuid4().hex
        user.credits -= credits

        db.add(
            Task(
                id=task_id,
                user_id=user.id,
                installation_id=installation.installation_id,
                repository=repository,
                request=request,
                model=model,
                status="queued",
                chat_id=chat_id,
                language=language or user.language,
            )
        )
        db.add(
            UsageRecord(
                task_id=task_id,
                user_id=user.id,
                repository=repository,
                request=request,
                model=model,
                credits_reserved=credits,
                credits_used=0,
                status="reserved",
            )
        )
        db.commit()

        return TaskReservation(task_id=task_id, remaining=user.credits)


def transition_task(
    task_id: str,
    from_status: str,
    to_status: str,
    *,
    branch: str | None = None,
    commit_sha: str | None = None,
    pull_request_number: int | None = None,
) -> bool:
    with SessionLocal() as db:
        task = db.scalar(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        if task is None or task.status != from_status:
            return False

        task.status = to_status
        if branch is not None:
            task.branch = branch
        if commit_sha is not None:
            task.commit_sha = commit_sha
        if pull_request_number is not None:
            task.pull_request_number = pull_request_number
        db.commit()
        return True


def complete_task(task_id: str, model: str) -> None:
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None:
            raise BillingError("Task not found")

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)

        usage = db.scalar(
            select(UsageRecord).where(UsageRecord.task_id == task_id).with_for_update()
        )
        if usage is not None:
            usage.model = model
            usage.credits_used = usage.credits_reserved
            usage.status = "completed"

        db.commit()


def fail_task(task_id: str, model: str, error: str, *, refund: bool) -> None:
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None:
            return

        task.status = "failed"
        task.error = error[:4000]
        task.completed_at = datetime.now(timezone.utc)

        usage = db.scalar(
            select(UsageRecord).where(UsageRecord.task_id == task_id).with_for_update()
        )
        if usage is not None:
            usage.model = model
            if refund:
                task_user = db.scalar(
                    select(User).where(User.id == task.user_id).with_for_update()
                )
                if task_user is not None:
                    task_user.credits += max(0, usage.credits_reserved - usage.credits_used)
                usage.status = "refunded"
            else:
                usage.status = "failed"

        db.commit()
