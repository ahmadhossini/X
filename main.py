from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time

import uvicorn
from telebot import TeleBot

from api.main import app
from bot.main import build_bot
from bot.telegram_polling_lock import TelegramPollingLock

# Railway may classify stderr output as errors in some log views. Keep standard
# application logs on stdout and replace any earlier root-handler setup.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

_bot_running = False
_stop_event = threading.Event()
_worker_stop_event = threading.Event()
_bot_lock = threading.Lock()
_worker_lock = threading.Lock()
_telegram_bot: TeleBot | None = None


def start_worker_process() -> subprocess.Popen:
    """Start ARQ and fail fast if it cannot stay alive during startup."""
    logger.info("Starting ARQ worker process")
    process = subprocess.Popen(
        ["arq", "app.workers.arq_worker.WorkerSettings"],
    )
    # Catch import/configuration failures before the API starts serving requests.
    time.sleep(2)
    return_code = process.poll()
    if return_code is not None:
        raise RuntimeError(
            f"ARQ worker exited during startup with code {return_code}"
        )
    logger.info("ARQ worker process started (pid=%s)", process.pid)
    return process


def stop_worker_process(process: subprocess.Popen) -> None:
    """Gracefully stop the ARQ child when the service shuts down."""
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


def run_worker_supervisor(process_holder: dict[str, subprocess.Popen]) -> None:
    """Restart ARQ if it crashes after startup instead of leaving jobs unprocessed."""
    delay = 2
    while not _worker_stop_event.wait(5):
        with _worker_lock:
            process = process_holder["process"]
        return_code = process.poll()
        if return_code is None:
            continue

        logger.error(
            "ARQ worker exited unexpectedly (code=%s); restarting",
            return_code,
        )
        while not _worker_stop_event.is_set():
            try:
                replacement = start_worker_process()
            except Exception:
                logger.exception(
                    "ARQ worker restart failed; retrying in %s seconds",
                    delay,
                )
                if _worker_stop_event.wait(delay):
                    return
                delay = min(delay * 2, 60)
                continue

            with _worker_lock:
                process_holder["process"] = replacement
            delay = 2
            break


def start_bot() -> None:
    global _bot_running, _telegram_bot

    with _bot_lock:
        if _bot_running:
            logger.warning("Telegram bot already running")
            return
        _bot_running = True

    polling_lock = TelegramPollingLock()
    lock_acquired = False
    try:
        lock_acquired = polling_lock.acquire()
        if not lock_acquired:
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
        if lock_acquired:
            polling_lock.release()
        _bot_running = False


def run_bot_supervisor() -> None:
    """Restart the Telegram bot if startup or polling exits unexpectedly."""
    delay = 2
    while not _stop_event.is_set():
        try:
            start_bot()
            if _stop_event.is_set():
                break
            logger.warning("Telegram bot exited unexpectedly; retrying in %s seconds", delay)
        except Exception:
            if _stop_event.is_set():
                break
            logger.exception(
                "Telegram bot supervisor caught an unexpected failure; retrying in %s seconds",
                delay,
            )

        if _stop_event.wait(delay):
            break
        delay = min(delay * 2, 60)


def shutdown_handler(signum, frame) -> None:
    logger.info("Shutdown signal received: %s", signum)
    _stop_event.set()
    _worker_stop_event.set()
    if _telegram_bot:
        logger.info("Stopping Telegram bot...")
        _telegram_bot.stop_bot()
        time.sleep(2)
    else:
        logger.warning("Telegram bot instance not found for graceful shutdown.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    worker_state = {"process": start_worker_process()}
    worker_thread = threading.Thread(
        target=run_worker_supervisor,
        args=(worker_state,),
        name="arq-worker-supervisor",
        daemon=True,
    )
    try:
        worker_thread.start()
        bot_thread = threading.Thread(
            target=run_bot_supervisor,
            name="telegram-bot",
            daemon=True,
        )
        bot_thread.start()

        port = int(os.getenv("PORT", "10000"))
        # Keep Uvicorn on the same stdout-based logging setup above.
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_config=None,
        )
    finally:
        _worker_stop_event.set()
        worker_thread.join(timeout=10)
        with _worker_lock:
            worker_process = worker_state["process"]
        stop_worker_process(worker_process)
