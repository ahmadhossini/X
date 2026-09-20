from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from datetime import datetime, timezone

from database.models import GitHubInstallation
from database.session import SessionLocal

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


def _workflow_run_fields(payload: dict[str, Any]) -> tuple[str, str, str | None, str | None, int | None, str | None, int | None]:
    repository = str((payload.get("repository") or {}).get("full_name") or "")
    workflow_run = payload.get("workflow_run") or {}
    head_sha = str(workflow_run.get("head_sha") or "")
    status = str(workflow_run.get("status") or "") or None
    conclusion = str(workflow_run.get("conclusion") or "") or None
    run_id = workflow_run.get("id")
    run_url = workflow_run.get("html_url")
    installation_id = (payload.get("installation") or {}).get("id")
    return (
        repository, head_sha, status, conclusion,
        int(run_id) if run_id is not None else None,
        str(run_url) if run_url else None,
        int(installation_id) if installation_id is not None else None,
    )


async def _handle_ping(payload: dict[str, Any]) -> None:
    logger.info("GitHub ping event received")


async def _handle_push(payload: dict[str, Any]) -> None:
    repository = (payload.get("repository") or {}).get("full_name")
    logger.info("GitHub push event received repository=%s", repository)


async def _handle_pull_request(payload: dict[str, Any]) -> None:
    repository = (payload.get("repository") or {}).get("full_name")
    action = payload.get("action") or "unknown"
    number = (payload.get("pull_request") or {}).get("number")
    logger.info(
        "GitHub pull_request event received repository=%s action=%s number=%s",
        repository,
        action,
        number,
    )


async def _handle_workflow_run(payload: dict[str, Any]) -> None:
    repository, head_sha, status, conclusion, run_id, run_url, installation_id = _workflow_run_fields(payload)
    action = str(payload.get("action") or "unknown")
    workflow = (payload.get("workflow_run") or {}).get("name")

    if repository and head_sha and installation_id:
        with SessionLocal() as db:
            tasks = list(
                db.query(Task)
                .filter(Task.repository == repository)
                .filter(Task.installation_id == int(installation_id))
                .filter(Task.commit_sha == head_sha)
                .all()
            )
            for task in tasks:
                task.ci_status = status
                task.ci_conclusion = conclusion
                task.ci_run_id = int(run_id) if run_id is not None else None
                task.ci_url = str(run_url)[:1024] if run_url else None
                task.ci_updated_at = datetime.now(timezone.utc)
            if tasks:
                db.commit()
                logger.info(
                    "Updated CI status for task(s) count=%s repository=%s commit=%s status=%s conclusion=%s",
                    len(tasks), repository, head_sha[:12], status, conclusion,
                )

    logger.info(
        "GitHub workflow_run event received repository=%s action=%s workflow=%s status=%s conclusion=%s",
        repository, action, workflow, status, conclusion,
    )


async def _handle_installation(payload: dict[str, Any]) -> None:
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    action = payload.get("action")
    if not installation_id:
        logger.warning("GitHub installation event has no installation id")
        return

    if action not in {"deleted", "suspend"}:
        logger.info("GitHub installation event received action=%s installation_id=%s", action, installation_id)
        return

    with SessionLocal() as db:
        record = (
            db.query(GitHubInstallation)
            .filter(GitHubInstallation.installation_id == int(installation_id))
            .first()
        )
        if record:
            record.active = False
            db.commit()
            logger.info(
                "GitHub installation deactivated installation_id=%s action=%s",
                installation_id,
                action,
            )


_HANDLERS: dict[str, EventHandler] = {
    "ping": _handle_ping,
    "push": _handle_push,
    "pull_request": _handle_pull_request,
    "workflow_run": _handle_workflow_run,
    "installation": _handle_installation,
}


async def route_github_event(payload: dict[str, Any]) -> bool:
    """Dispatch a verified GitHub event to its explicit handler.

    Returns True when the event type is supported. Unknown event types are
    intentionally ignored after being persisted, so adding a new GitHub event
    never creates an accidental side effect.
    """
    event_type = str(payload.get("_event_type") or "unknown")
    handler = _HANDLERS.get(event_type)
    if handler is None:
        logger.info("Ignoring unsupported GitHub event type=%s", event_type)
        return False

    await handler(payload)
    return True
