from __future__ import annotations

import logging
import os
import signal
import threading

import uvicorn

from api.main import app
from bot.task_queue import worker_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_stop_event = threading.Event()


def start_task_worker() -> None:
    """Keep the persistent worker alive if an unexpected worker error occurs."""
    restart_delay = 2.0
    while not _stop_event.is_set():
        try:
            worker_loop(_stop_event)
            return
        except Exception:
            logger.exception("Persistent task worker crashed; restarting")
            if _stop_event.wait(restart_delay):
                return
            restart_delay = min(restart_delay * 2, 30.0)


def shutdown_handler(signum, frame) -> None:
    logger.info("Shutdown signal received: %s", signum)
    _stop_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    task_worker_thread = threading.Thread(
        target=start_task_worker,
        name="persistent-task-worker",
        daemon=True,
    )
    task_worker_thread.start()

    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
