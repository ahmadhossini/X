from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bot.services.group_settings_store import store
from core.config import settings
from database.session import init_db
from market.service import crypto_market

app = FastAPI(title="XAI MASTER API", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
    return {"status": "ok", "version": "3.1.0"}


@app.get("/api/market/crypto")
async def crypto_prices() -> list[dict]:
    return await crypto_market()


FEATURES = {
    "anti_spam",
    "anti_flood",
    "anti_link",
    "forward_lock",
    "mention_lock",
    "hashtag_lock",
    "phone_lock",
    "profanity_filter",
    "drug_filter",
    "nsfw_filter",
}


def _telegram_check_string(init_data: str) -> tuple[str, dict[str, str]]:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(pairs.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        settings.bot_token.encode(),
        hashlib.sha256,
    ).digest()
    calculated = hmac.new(
        secret_key,
        check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    auth_date = int(pairs.get("auth_date", "0"))
    if not auth_date or time.time() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Expired Telegram init data")

    return pairs.get("user", ""), pairs


def _authorized_admin(chat_id: int, init_data: str) -> int:
    user_json, _ = _telegram_check_string(init_data)
    if not user_json:
        raise HTTPException(status_code=401, detail="Telegram user missing")

    try:
        user = json.loads(user_json)
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid Telegram user")

    try:
        member = app.state.bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Cannot verify group admin") from exc

    if member.status not in {"creator", "administrator"}:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user_id


class FeatureUpdate(BaseModel):
    feature: str
    enabled: bool


@app.get("/api/groups/{chat_id}/settings")
def get_group_settings(
    chat_id: int,
    x_telegram_init_data: str = Header(default=""),
):
    _authorized_admin(chat_id, x_telegram_init_data)
    return {"chat_id": chat_id, "settings": store.get(chat_id).__dict__}


@app.post("/api/groups/{chat_id}/settings")
def update_group_setting(
    chat_id: int,
    payload: FeatureUpdate,
    x_telegram_init_data: str = Header(default=""),
):
    _authorized_admin(chat_id, x_telegram_init_data)
    if payload.feature not in FEATURES:
        raise HTTPException(status_code=400, detail="Unknown feature")

    updated = store.set(chat_id, payload.feature, payload.enabled)
    return {"chat_id": chat_id, "settings": updated.__dict__}
