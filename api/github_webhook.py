from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.workers.queue import enqueue_github_event
from core.config import settings
from database.models import GitHubInstallation, WebhookEvent
from database.session import SessionLocal

router = APIRouter(prefix="/api/github", tags=["github"])


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, str]:
    body = await request.body()
    secret = settings.github_webhook_secret.encode("utf-8")

    if not secret:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET is not configured")
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing GitHub signature")
    if not x_github_delivery:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery id")

    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = x_github_event or "unknown"
    with SessionLocal() as db:
        existing = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == x_github_delivery).first()
        if existing and existing.processed:
            return {"status": "duplicate", "event": event}

        if existing is None:
            record = WebhookEvent(
                delivery_id=x_github_delivery,
                provider="github",
                event_type=event,
                payload=json.dumps(payload, separators=(",", ":")),
                processed=False,
            )
            db.add(record)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.query(WebhookEvent).filter(WebhookEvent.delivery_id == x_github_delivery).first()
                if existing and existing.processed:
                    return {"status": "duplicate", "event": event}
        else:
            existing.payload = json.dumps(payload, separators=(",", ":"))
            existing.event_type = event
            existing.processed = False
            db.commit()
    payload["_delivery_id"] = x_github_delivery
    payload["_event_type"] = event
    try:
        await enqueue_github_event(payload)
    except Exception:
        with SessionLocal() as db:
            db.query(WebhookEvent).filter(WebhookEvent.delivery_id == x_github_delivery).update({"processed": False})
            db.commit()
        raise HTTPException(status_code=503, detail="Event queue is unavailable")

    return {"status": "queued", "event": event}
