from __future__ import annotations

import threading

import uvicorn

from api.main import app
from bot.main import run_bot
from core.config import settings


if __name__ == "__main__":
    if settings.bot_token:
        threading.Thread(target=run_bot, daemon=True, name="telegram-bot").start()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
