from __future__ import annotations

import logging
import os
import signal
import subprocess
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


def start_worker_process() -> subprocess.Popen:
    """Run ARQ beside the API and Telegram bot in the same Railway service."""
    logger.info("Starting ARQ worker process")
    process = subprocess.Popen(
        ["arq", "app.workers.arq_worker.WorkerSettings"],
    )
    # Fail fast if the worker immediately exits (for example, due to a bad
    # import or missing configuration) instead of serving an API with a dead queue.
    time.sleep(2)
    return_code = process.poll()
    if return_code is not None:
        raise RuntimeError(
            f"ARQ worker exited during startup with code {return_code}"
        )
    logger.info("ARQ worker process started (pid=%s)", process.pid)
    return process


def stop_worker_process(process: subprocess.Popen) -> None:
    """Gracefully stop the ARQ child when Railway shuts down this container."""
    if process.poll() is not None:
        return
    logger.info("Stopping ARQ worker process")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        logger.warning("ARQ worker did not stop in time; killing it")
        process.kill()
        process.wait(timeout=5)


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


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    worker_process = start_worker_process()
    try:
        bot_thread = threading.Thread(
            target=start_bot,
            name="telegram-bot",
            daemon=True,
        )
        bot_thread.start()

        port = int(os.getenv("PORT", "10000"))
        uvicorn.run(app, host="0.0.0.0", port=port)
    finally:
        stop_worker_process(worker_process)
