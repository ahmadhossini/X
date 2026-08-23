from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot.services.group_settings_store import store
from bot.services.user_language import get_user_language
from core.config import settings
from database.session import init_db
from market.service import crypto_market

app = FastAPI(title="XAI MASTER API", version="3.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
    app.mount("/miniapp", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="miniapp")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.on_event("startup")
def setup_bot_client() -> None:
    from telebot import TeleBot
    app.state.bot = TeleBot(settings.bot_token)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "XAI MASTER V3", "status": "online"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "3.2.0"}


@app.get("/api/market/crypto")
async def crypto_prices() -> list[dict]:
    return await crypto_market()


FEATURES = {
    "anti_spam",
    "anti_flood",
    "anti_link",
    "media_lock",
    "forward_lock",
    "mention_lock",
    "hashtag_lock",
    "phone_lock",
    "profanity_filter",
    "drug_filter",
    "nsfw_filter",
    "force_join",
    "welcome",
    "goodbye",
    "clean_deleted_accounts",
    "clean_bots",
    "work_hours",
    "global_mute",
    "auto_pin",
    "auto_answer",
    "ai_chat",
    "statistics",
}


def _telegram_check_string(init_data: str) -> tuple[dict, dict[str, str]]:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    auth_date = int(pairs.get("auth_date", "0"))
    if not auth_date or time.time() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Expired Telegram init data")

    raw_user = pairs.get("user", "")
    if not raw_user:
        raise HTTPException(status_code=401, detail="Telegram user missing")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram user") from exc
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(status_code=401, detail="Invalid Telegram user")
    return user, pairs


def _user_from_init_data(init_data: str) -> dict:
    user, _ = _telegram_check_string(init_data)
    return user


def _authorized_admin(chat_id: int, init_data: str) -> int:
    user = _user_from_init_data(init_data)
    user_id = int(user["id"])
    try:
        member = app.state.bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Cannot verify group admin") from exc
    if member.status not in {"creator", "administrator"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


def _group_snapshot(chat_id: int, user_id: int) -> dict:
    try:
        member = app.state.bot.get_chat_member(chat_id, user_id)
    except Exception:
        return {}
    if member.status not in {"creator", "administrator"}:
        return {}

    try:
        chat = app.state.bot.get_chat(chat_id)
        title = getattr(chat, "title", "") or "Group"
        username = getattr(chat, "username", None)
        photo_file_id = getattr(getattr(chat, "photo", None), "big_file_id", None)
    except Exception:
        return {}

    try:
        member_count = int(app.state.bot.get_chat_member_count(chat_id))
    except Exception:
        member_count = 0

    return {
        "id": chat_id,
        "title": title,
        "username": username,
        "member_count": member_count,
        "photo_url": f"/api/groups/{chat_id}/photo" if photo_file_id else None,
    }


@app.get("/api/me")
def get_me(x_telegram_init_data: str = Header(default="")):
    user = _user_from_init_data(x_telegram_init_data)
    user_id = int(user["id"])
    language = get_user_language(user_id) or "fa"
    return {
        "id": user_id,
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username"),
        "photo_url": user.get("photo_url"),
        "language": language,
    }


@app.get("/api/me/groups")
def get_my_groups(x_telegram_init_data: str = Header(default="")):
    user = _user_from_init_data(x_telegram_init_data)
    user_id = int(user["id"])
    groups: list[dict] = []

    # Known managed groups are stored by the group settings service. Each group
    # is checked against Telegram before it is shown to the current user.
    try:
        known_ids = [int(value) for value in store._load().keys()]
    except Exception:
        known_ids = []

    for chat_id in known_ids:
        snapshot = _group_snapshot(chat_id, user_id)
        if snapshot:
            groups.append(snapshot)

    groups.sort(key=lambda item: item["title"].lower())
    return {"groups": groups}


@app.get("/api/groups/{chat_id}")
def get_group(chat_id: int, x_telegram_init_data: str = Header(default="")):
    user_id = _authorized_admin(chat_id, x_telegram_init_data)
    snapshot = _group_snapshot(chat_id, user_id)
    if not snapshot:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"group": snapshot, "settings": store.get(chat_id).__dict__}


@app.get("/api/groups/{chat_id}/photo")
def get_group_photo(chat_id: int, x_telegram_init_data: str = Header(default="")):
    _authorized_admin(chat_id, x_telegram_init_data)
    try:
        chat = app.state.bot.get_chat(chat_id)
        file_id = getattr(getattr(chat, "photo", None), "big_file_id", None)
        if not file_id:
            raise HTTPException(status_code=404, detail="Group photo not found")
        file_info = app.state.bot.get_file(file_id)
        content = app.state.bot.download_file(file_info.file_path)
        return Response(content=content, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Group photo not found") from exc


class FeatureUpdate(BaseModel):
    feature: str
    enabled: bool


class GroupConfigUpdate(BaseModel):
    force_join_count: int | None = Field(default=None, ge=0, le=20)
    force_join_channels: list[str] | None = None


@app.get("/api/groups/{chat_id}/settings")
def get_group_settings(chat_id: int, x_telegram_init_data: str = Header(default="")):
    _authorized_admin(chat_id, x_telegram_init_data)
    return {"chat_id": chat_id, "settings": store.get(chat_id).__dict__}


@app.post("/api/groups/{chat_id}/settings")
def update_group_setting(chat_id: int, payload: FeatureUpdate, x_telegram_init_data: str = Header(default="")):
    _authorized_admin(chat_id, x_telegram_init_data)
    if payload.feature not in FEATURES:
        raise HTTPException(status_code=400, detail="Unknown feature")
    updated = store.set(chat_id, payload.feature, payload.enabled)
    return {"chat_id": chat_id, "settings": updated.__dict__}


@app.post("/api/groups/{chat_id}/config")
def update_group_config(chat_id: int, payload: GroupConfigUpdate, x_telegram_init_data: str = Header(default="")):
    _authorized_admin(chat_id, x_telegram_init_data)
    updated = store.update_config(
        chat_id,
        force_join_count=payload.force_join_count,
        force_join_channels=payload.force_join_channels,
    )
    return {"chat_id": chat_id, "settings": updated.__dict__}
