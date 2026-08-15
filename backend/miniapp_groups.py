from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.chat_registry import registry
from backend.miniapp_api import _identity
from backend.telegram_api import TelegramAPI, TelegramAPIError
from bot.services.group_settings_store import store

router = APIRouter(prefix="/api/miniapp", tags=["miniapp-groups"])


class SettingUpdate(BaseModel):
    feature: str
    enabled: bool


async def _is_admin(user_id: int, chat_id: int) -> bool:
    try:
        member = await TelegramAPI().get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.get("status") in {"administrator", "creator"}


@router.get("/groups")
async def list_groups(x_telegram_init_data: str = Header(default="")):
    user = _identity(x_telegram_init_data)
    result = []
    for chat in registry.all():
        if chat.chat_type not in {"group", "supergroup", "channel"}:
            continue
        if await _is_admin(user["id"], chat.chat_id):
            settings = store.get(chat.chat_id)
            enabled = sum(bool(value) for value in vars(settings).values())
            result.append({"chat_id": chat.chat_id, "title": chat.title, "username": chat.username, "type": chat.chat_type, "enabled_features": enabled, "settings": vars(settings)})
    return {"user_id": user["id"], "groups": result}


@router.get("/groups/{chat_id}/settings")
async def get_group_settings(chat_id: int, x_telegram_init_data: str = Header(default="")):
    user = _identity(x_telegram_init_data)
    if not await _is_admin(user["id"], chat_id):
        raise HTTPException(status_code=403, detail="You are not an administrator of this chat")
    return {"chat_id": chat_id, "settings": vars(store.get(chat_id))}


@router.patch("/groups/{chat_id}/settings")
async def update_group_setting(chat_id: int, update: SettingUpdate, x_telegram_init_data: str = Header(default="")):
    user = _identity(x_telegram_init_data)
    if not await _is_admin(user["id"], chat_id):
        raise HTTPException(status_code=403, detail="You are not an administrator of this chat")
    try:
        settings = store.set(chat_id, update.feature, update.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"chat_id": chat_id, "settings": vars(settings)}
