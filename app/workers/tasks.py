from __future__ import annotations

import logging
from typing import Any

from database.models import WebhookEvent
from database.session import SessionLocal

logger = logging.getLogger(__name__)


async def process_github_event(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """Process a GitHub event outside the webhook request lifecycle."""
    delivery_id = str(payload.get("_delivery_id") or "")
    try:
        if delivery_id:
            with SessionLocal() as db:
                event = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first()
                if event:
                    event.processed = True
                    db.commit()
    except Exception:
        logger.exception("Failed to finalize GitHub webhook event %s", delivery_id)
        raise
