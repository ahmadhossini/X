from __future__ import annotations

import logging
import os
import threading

import uvicorn

from api.main import app
from bot.main import run_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def start_bot() -> None:
    try:
        run_bot()
    except Exception:
        logger.exception("Telegram bot stopped")
        raise


if __name__ == "__main__":
    # Render runs the HTTP server in the foreground while Telegram polling
    # runs in a dedicated thread. This keeps /health and the bot alive together.
    bot_thread = threading.Thread(target=start_bot, name="telegram-bot", daemon=True)
    bot_thread.start()

    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
