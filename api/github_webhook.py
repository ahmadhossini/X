from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from core.config import settings
from database.models import GitHubInstallation
from database.session import SessionLocal

router = APIRouter(prefix="/api/github", tags=["github"])


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, str]:
    body = await request.body()
    secret = settings.github_webhook_secret.encode("utf-8")

    if not secret:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET is not configured")
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing GitHub signature")

    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    event = x_github_event or "unknown"
    if event == "installation":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        installation_id = (payload.get("installation") or {}).get("id")
        action = payload.get("action")
        if installation_id and action in {"deleted", "suspend"}:
            with SessionLocal() as db:
                db.query(GitHubInstallation).filter(GitHubInstallation.installation_id == installation_id).update({"active": False})
                db.commit()

    return {"status": "ok", "event": event}
