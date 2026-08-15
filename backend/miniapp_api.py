from __future__ import annotations

import json
import os

from fastapi import APIRouter, Header, HTTPException

from backend.miniapp_auth import validate_telegram_init_data

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


def _identity(init_data: str) -> dict:
    try:
        pairs = validate_telegram_init_data(init_data, os.environ["BOT_TOKEN"])
        user = json.loads(pairs.get("user", "{}"))
        if not user.get("id"):
            raise ValueError("Telegram user missing")
        return user
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram session") from exc


@router.get("/me")
def me(x_telegram_init_data: str = Header(default="")):
    user = _identity(x_telegram_init_data)
    return {"id": user["id"], "first_name": user.get("first_name", ""), "last_name": user.get("last_name"), "username": user.get("username"), "photo_url": user.get("photo_url"), "language_code": user.get("language_code")}


@router.get("/groups")
def groups(x_telegram_init_data: str = Header(default="")):
    user = _identity(x_telegram_init_data)
    # Group discovery is deliberately kept server-side. Never accept chat_id
    # from the client as proof of access; the next layer verifies membership
    # with Telegram before returning settings for a chat.
    return {"user_id": user["id"], "groups": []}
