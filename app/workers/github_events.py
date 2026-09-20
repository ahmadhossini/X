from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from database.models import GitHubInstallation
from database.session import SessionLocal

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


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
    repository = (payload.get("repository") or {}).get("full_name")
    action = payload.get("action") or "unknown"
    workflow = (payload.get("workflow_run") or {}).get("name")
    logger.info(
        "GitHub workflow_run event received repository=%s action=%s workflow=%s",
        repository,
        action,
        workflow,
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
