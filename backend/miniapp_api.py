from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.chat_registry import registry
from backend.chat_stats import stats
from backend.miniapp_auth import validate_telegram_init_data
from bot.services.group_settings_store import ALIASES, store

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


async def _telegram(method: str, **params):
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Telegram integration is not configured")
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(
            f"https://api.telegram.org/bot{token}/{method}",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise HTTPException(status_code=502, detail="Telegram API error")
        return data["result"]


async def _admin(user_id: int, chat_id: int) -> bool:
    try:
        member = await _telegram("getChatMember", chat_id=chat_id, user_id=user_id)
        return member.get("status") in {"creator", "administrator"}
    except Exception:
        return False


def _require_init_data(value: str) -> str:
    if not value:
        raise HTTPException(status_code=401, detail="Telegram session is required")
    return value


@router.get("/me")
def me(x_telegram_init_data: str = Header(default="")):
    user = _identity(_require_init_data(x_telegram_init_data))
    return {
        "id": user["id"],
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name"),
        "username": user.get("username"),
        "photo_url": user.get("photo_url"),
        "language_code": user.get("language_code"),
    }


@router.get("/groups")
async def groups(x_telegram_init_data: str = Header(default="")):
    user = _identity(_require_init_data(x_telegram_init_data))
    output = []
    for chat in registry.all():
        if await _admin(user["id"], chat.chat_id):
            try:
                info = await _telegram("getChat", chat_id=chat.chat_id)
            except HTTPException:
                info = {}
            snapshot = stats.get(chat.chat_id)
            output.append(
                {
                    "chat_id": chat.chat_id,
                    "title": chat.title,
                    "type": chat.chat_type,
                    "username": chat.username,
                    "member_count": info.get("members_count"),
                    "message_count": snapshot["messages"],
                    "deleted_count": snapshot["deleted"],
                }
            )
    return {"groups": output}


async def _authorized_chat(chat_id: int, init_data: str) -> dict:
    user = _identity(_require_init_data(init_data))
    if not await _admin(user["id"], chat_id):
        raise HTTPException(status_code=403, detail="You are not an administrator of this chat")
    record = next((chat for chat in registry.all() if chat.chat_id == chat_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="Chat not found")
    return record


@router.get("/groups/{chat_id}")
async def group(chat_id: int, x_telegram_init_data: str = Header(default="")):
    record = await _authorized_chat(chat_id, x_telegram_init_data)
    try:
        info = await _telegram("getChat", chat_id=chat_id)
    except HTTPException:
        info = {}
    return {
        "chat_id": chat_id,
        "title": record.title,
        "type": record.chat_type,
        "username": record.username,
        "member_count": info.get("members_count"),
        "stats": stats.get(chat_id),
        "telegram": info,
    }


@router.get("/groups/{chat_id}/stats")
async def group_stats(chat_id: int, x_telegram_init_data: str = Header(default="")):
    await _authorized_chat(chat_id, x_telegram_init_data)
    return stats.get(chat_id)


class SettingChange(BaseModel):
    feature: str = Field(min_length=1, max_length=64)
    enabled: bool


@router.get("/groups/{chat_id}/settings")
async def group_settings(chat_id: int, x_telegram_init_data: str = Header(default="")):
    await _authorized_chat(chat_id, x_telegram_init_data)
    from dataclasses import asdict

    return asdict(store.get(chat_id))


async def _update_setting(
    chat_id: int,
    change: SettingChange,
    init_data: str,
):
    await _authorized_chat(chat_id, init_data)
    canonical = ALIASES.get(change.feature, change.feature)
    try:
        from dataclasses import asdict

        return asdict(store.set(chat_id, canonical, change.enabled))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/groups/{chat_id}/settings")
async def update_group_setting(
    chat_id: int,
    change: SettingChange,
    x_telegram_init_data: str = Header(default=""),
):
    return await _update_setting(chat_id, change, x_telegram_init_data)


@router.put("/groups/{chat_id}/settings")
async def update_group_setting_compat(
    chat_id: int,
    change: SettingChange,
    x_telegram_init_data: str = Header(default=""),
):
    """Compatibility endpoint for the first V3 Mini App client."""
    return await _update_setting(chat_id, change, x_telegram_init_data)
