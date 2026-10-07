from __future__ import annotations

import logging
import os
import signal
import threading
import time

import uvicorn
from telebot import TeleBot

from api.main import app
from bot.main import build_bot
from bot.telegram_polling_lock import TelegramPollingLock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_bot_running = False
_stop_event = threading.Event()
_bot_lock = threading.Lock()
_telegram_bot: TeleBot | None = None


def start_bot() -> None:
    global _bot_running, _telegram_bot

    with _bot_lock:
        if _bot_running:
            logger.warning("Telegram bot already running")
            return
        _bot_running = True

    polling_lock = TelegramPollingLock()
    try:
        if not polling_lock.acquire():
            logger.error("Another XAI Code Agent instance already owns the Telegram polling lock")
            return
        logger.info("Telegram bot starting")
        _telegram_bot = build_bot()
        logger.info("Telegram bot polling started")
        _telegram_bot.infinity_polling(skip_pending=True)
    except Exception:
        logger.exception("Telegram bot stopped")
        raise
    finally:
        polling_lock.release()
        _bot_running = False


def shutdown_handler(signum, frame) -> None:
    logger.info("Shutdown signal received: %s", signum)
    _stop_event.set()
    if _telegram_bot:
        logger.info("Stopping Telegram bot...")
        _telegram_bot.stop_bot()
        time.sleep(2)
    else:
        logger.warning("Telegram bot instance not found for graceful shutdown.")

    worker = _arq_worker
    loop = _arq_loop


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
