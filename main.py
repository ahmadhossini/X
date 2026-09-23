from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
import time

from arq.worker import Worker

import uvicorn
from telebot import TeleBot

from api.main import app
from bot.main import build_bot
from app.workers.arq_worker import WorkerSettings
from bot.telegram_polling_lock import TelegramPollingLock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_bot_running = False
_stop_event = threading.Event()
_bot_lock = threading.Lock()
_telegram_bot: TeleBot | None = None
_arq_worker: Worker | None = None
_arq_loop: asyncio.AbstractEventLoop | None = None


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


def start_arq_worker() -> None:
    global _arq_worker, _arq_loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    worker = Worker(
        functions=WorkerSettings.functions,
        cron_jobs=WorkerSettings.cron_jobs,
        redis_settings=WorkerSettings.redis_settings,
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        handle_signals=False,
    )
    _arq_loop = loop
    _arq_worker = worker
    logger.info("ARQ worker starting")
    try:
        loop.run_until_complete(worker.async_run())
    except asyncio.CancelledError:
        logger.info("ARQ worker cancelled")
    except Exception:
        logger.exception("ARQ worker stopped unexpectedly")
        raise
    finally:
        try:
            loop.run_until_complete(worker.close())
        except Exception:
            logger.exception("Failed to close ARQ worker cleanly")
        _arq_worker = None
        _arq_loop = None
        loop.close()


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
    if worker and loop and not loop.is_closed():
        logger.info("Stopping ARQ worker...")
        loop.call_soon_threadsafe(worker.handle_sig, signal.SIGTERM)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    bot_thread = threading.Thread(
        target=start_bot,
        name="telegram-bot",
        daemon=True,
    )
    bot_thread.start()

    worker_thread = threading.Thread(
        target=start_arq_worker,
        name="arq-worker",
        daemon=True,
    )
    worker_thread.start()

    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
