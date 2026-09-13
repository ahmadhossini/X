from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from telebot import TeleBot, types

from api.github_connect import router as github_connect_router
from api.github_webhook import router as github_webhook_router
from api.miniapp import router as miniapp_router
from api.miniapp_billing import router as miniapp_billing_router
from api.miniapp_connect import router as miniapp_connect_router
from api.payments import router as payments_router
from bot.main import build_bot
from code_agent.routes import router as code_agent_router
from core.config import settings
from database.session import init_db


def _telegram_webhook_secret() -> str:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    return hashlib.sha256((settings.bot_token + ":xai-telegram-webhook").encode("utf-8")).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bot = build_bot()
    if not settings.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL is not configured")
    webhook_url = f"{settings.public_base_url}/api/telegram/webhook"
    secret = _telegram_webhook_secret()
    bot.set_webhook(
        url=webhook_url,
        secret_token=secret,
        allowed_updates=["message", "callback_query", "pre_checkout_query", "my_chat_member"],
        drop_pending_updates=False,
        max_connections=20,
    )
    app.state.telegram_bot = bot
    app.state.telegram_webhook_secret = secret
    yield
    try:
        bot.stop_bot()
    except Exception:
        pass


app = FastAPI(title="XAI Code Agent API", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(code_agent_router)
app.include_router(github_connect_router)
app.include_router(github_webhook_router)
app.include_router(miniapp_router)
app.include_router(miniapp_billing_router)
app.include_router(miniapp_connect_router)
app.include_router(payments_router)
app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")


@app.post("/api/telegram/webhook")
def telegram_webhook(
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    bot: TeleBot | None = getattr(app.state, "telegram_bot", None)
    secret = getattr(app.state, "telegram_webhook_secret", "")
    if bot is None or not secret:
        raise HTTPException(status_code=503, detail="Telegram bot is not ready")
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, secret):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="Invalid Telegram update")
    parsed = types.Update.de_json(update)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Invalid Telegram update")
    bot.process_new_updates([parsed])
    return {"ok": True}


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "XAI Code Agent", "status": "online"}


@app.get("/miniapp")
def miniapp() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/", status_code=307)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "code_agent": "embedded", "github": "enabled", "telegram": "webhook"}
