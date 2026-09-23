from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from core.config import settings
from database.models import GitHubInstallation, Task, UsageRecord, User
from database.session import SessionLocal


class BillingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskReservation:
    task_id: str


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

        installation = db.scalar(
            select(GitHubInstallation)
            .where(
                GitHubInstallation.user_id == user.id,
                GitHubInstallation.active.is_(True),
            )
            .order_by(GitHubInstallation.updated_at.desc())
        )
        if installation is None:
            raise BillingError("GitHub not connected")

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

    return TaskReservation(task_id=task_id)
