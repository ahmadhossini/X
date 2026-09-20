from __future__ import annotations

import logging
from typing import Any

from app.workers.github_events import route_github_event
from database.models import WebhookEvent
from database.session import SessionLocal

logger = logging.getLogger(__name__)


async def process_github_event(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """Route a GitHub event and mark it processed only after successful handling."""
    delivery_id = str(payload.get("_delivery_id") or "")
    event_type = str(payload.get("_event_type") or "unknown")
    if not delivery_id:
        raise ValueError("GitHub event delivery id is required")

    with SessionLocal() as db:
        event = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first()
        if event is None:
            raise ValueError(f"GitHub webhook record not found: {delivery_id}")
        if event.processed:
            logger.info("GitHub event already processed delivery_id=%s", delivery_id)
            return

    try:
        await route_github_event({**payload, "_event_type": event_type})
    except Exception:
        logger.exception(
            "GitHub event handler failed delivery_id=%s event_type=%s",
            delivery_id,
            event_type,
        )
        raise

    with SessionLocal() as db:
        event = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first()
        if event is None:
            raise ValueError(f"GitHub webhook record disappeared: {delivery_id}")
        if not event.processed:
            event.processed = True
            db.commit()
    logger.info(
        "GitHub event processed delivery_id=%s event_type=%s",
        delivery_id,
        event_type,
    )
