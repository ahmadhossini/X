from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bot.services.user_language import get_user_language
from core.config import settings
from database.session import init_db
from market.service import crypto_market
from code_agent.routes import router as code_agent_router
from api.github_webhook import router as github_webhook_router

app = FastAPI(title="XAI MASTER API", version="3.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
    app.mount("/miniapp", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="miniapp")
app.include_router(code_agent_router)
app.include_router(github_webhook_router)

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
    return {"status": "ok", "version": "3.3.0", "code_agent": "embedded"}

@app.get("/api/market/crypto")
async def crypto_prices() -> list[dict]:
    return await crypto_market()

def _telegram_check_string(init_data: str) -> dict:
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
    return user

@app.get("/api/me")
def get_me(x_telegram_init_data: str = Header(default="")):
    user = _telegram_check_string(x_telegram_init_data)
    user_id = int(user["id"])
    return {"id": user_id, "first_name": user.get("first_name", ""), "last_name": user.get("last_name", ""), "username": user.get("username"), "photo_url": user.get("photo_url"), "language": get_user_language(user_id) or "fa"}
