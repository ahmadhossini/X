from __future__ import annotations

import logging
import threading
import time
import uuid

from redis import Redis
from redis.exceptions import RedisError

from core.config import settings

logger = logging.getLogger(__name__)

_LOCK_KEY = "xai:telegram:polling-lock"
_LOCK_TTL_MS = 90_000
_RENEW_INTERVAL = 30.0


class TelegramPollingLock:
    def __init__(self) -> None:
        self._token = uuid.uuid4().hex
        self._redis: Redis | None = None
        self._stop = threading.Event()
        self._renew_thread: threading.Thread | None = None

    def acquire(self) -> bool:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is required for Telegram polling lock")

        self._redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            acquired = bool(
                self._redis.set(
                    _LOCK_KEY,
                    self._token,
                    nx=True,
                    px=_LOCK_TTL_MS,
                )
            )
        except RedisError as exc:
            self._redis.close()
            self._redis = None
            raise RuntimeError(f"Redis is unavailable for Telegram polling lock: {exc}") from exc

        if not acquired:
            self._redis.close()
            self._redis = None
            return False

        self._renew_thread = threading.Thread(
            target=self._renew_loop,
            name="telegram-polling-lock-renewer",
            daemon=True,
        )
        self._renew_thread.start()
        return True

    def _renew_loop(self) -> None:
        while not self._stop.wait(_RENEW_INTERVAL):
            redis = self._redis
            if redis is None:
                return
            try:
                renewed = redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end",
                    1,
                    _LOCK_KEY,
                    self._token,
                    _LOCK_TTL_MS,
                )
                if not renewed:
                    logger.error("Telegram polling lock was lost")
                    return
            except RedisError:
                logger.exception("Failed to renew Telegram polling lock")
                return

    def release(self) -> None:
        self._stop.set()
        redis = self._redis
        self._redis = None
        if redis is None:
            return
        try:
            redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                _LOCK_KEY,
                self._token,
            )
        except RedisError:
            logger.exception("Failed to release Telegram polling lock")
        finally:
            redis.close()
