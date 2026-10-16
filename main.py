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

# Railway classifies stderr output as errors in some log views. Send standard
# application logs to stdout and replace any earlier root-handler setup.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

_bot_running = False
_stop_event = threading.Event()
_bot_lock = threading.Lock()
_telegram_bot: TeleBot | None = None
_worker_process: subprocess.Popen | None = None
_worker_process_lock = threading.Lock()


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

def run_worker_supervisor(initial_process: subprocess.Popen) -> None:
    """Restart ARQ if it exits after startup, using bounded exponential backoff."""
    global _worker_process

    process: subprocess.Popen | None = initial_process
    delay = 2
    started_at = time.monotonic()

    while not _stop_event.is_set():
        if process is not None and process.poll() is None:
            if _stop_event.wait(1):
                break
            continue

        if process is not None:
            return_code = process.poll()
            lifetime = time.monotonic() - started_at
            if lifetime >= 30:
                delay = 2
            else:
                delay = min(delay * 2, 60)
            logger.error(
                "ARQ worker exited unexpectedly (code=%s); restart scheduled",
                return_code,
            )
            process = None

        if _stop_event.is_set() or _stop_event.wait(delay):
            break

        try:
            process = start_worker_process()
            started_at = time.monotonic()
            with _worker_process_lock:
                _worker_process = process
            logger.info("ARQ worker supervisor restarted the worker")
        except Exception:
            logger.exception("ARQ worker restart failed; retrying in %s seconds", delay)
            delay = min(delay * 2, 60)



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
            # A normal return without shutdown is unexpected (e.g. lock failure
            # or polling loop exit); retry instead of leaving the service botless.
            logger.warning("Telegram bot exited unexpectedly; retrying in %s seconds", delay)
        except Exception:
            if _stop_event.is_set():
                break
            logger.exception("Telegram bot supervisor caught an unexpected failure; retrying in %s seconds", delay)

        if _stop_event.wait(delay):
            break
        delay = min(delay * 2, 60)


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

    _worker_process = start_worker_process()
    worker_process = _worker_process
    worker_supervisor_thread = threading.Thread(
        target=run_worker_supervisor,
        args=(worker_process,),
        name="arq-worker-supervisor",
        daemon=True,
    )
    try:
        worker_supervisor_thread.start()
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
        _stop_event.set()
        worker_supervisor_thread.join(timeout=15)
        with _worker_process_lock:
            current_worker = _worker_process
        if current_worker is not None:
            stop_worker_process(current_worker)
