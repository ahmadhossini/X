from __future__ import annotations

import logging
import os
import signal
import threading

import uvicorn

from api.main import app
from bot.main import run_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_bot_running = False
_stop_event = threading.Event()
_bot_lock = threading.Lock()


def start_bot() -> None:
    global _bot_running

    with _bot_lock:
        if _bot_running:
            logger.warning("Telegram bot already running")
            return
        _bot_running = True

    try:
        logger.info("Telegram bot starting")
        run_bot()
    except Exception:
        logger.exception("Telegram bot stopped")
        raise
    finally:
        _bot_running = False


def shutdown_handler(signum, frame) -> None:
    logger.info("Shutdown signal received: %s", signum)
    _stop_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    bot_thread = threading.Thread(
        target=start_bot,
        name="telegram-bot",
        daemon=True,
    )
    bot_thread.start()

    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
