from __future__ import annotations

from datetime import datetime, timezone

_limits: dict[tuple[int, int, str], tuple[str, int]] = {}

GROUP_LIMIT = 5
PRIVATE_LIMIT = 20


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_ai_limit(user_id: int, chat_id: int, private: bool) -> tuple[bool, int]:
    mode = "private" if private else "group"
    key = (user_id, chat_id, mode)
    day = _today()
    saved_day, count = _limits.get(key, (day, 0))
    if saved_day != day:
        count = 0

    limit = PRIVATE_LIMIT if private else GROUP_LIMIT
    if count >= limit:
        return False, 0

    count += 1
    _limits[key] = (day, count)
    return True, limit - count


def check_limit(user_id: int, mode: str) -> bool:
    key = (user_id, 0, mode)
    day = _today()
    saved_day, count = _limits.get(key, (day, 0))
    if saved_day != day:
        count = 0
    limit = GROUP_LIMIT if mode == "group" else PRIVATE_LIMIT
    return count < limit


def add_usage(user_id: int, mode: str) -> None:
    key = (user_id, 0, mode)
    day = _today()
    saved_day, count = _limits.get(key, (day, 0))
    if saved_day != day:
        count = 0
    _limits[key] = (day, count + 1)


def remaining(user_id: int, mode: str) -> int:
    key = (user_id, 0, mode)
    day = _today()
    saved_day, count = _limits.get(key, (day, 0))
    if saved_day != day:
        return GROUP_LIMIT if mode == "group" else PRIVATE_LIMIT
    limit = GROUP_LIMIT if mode == "group" else PRIVATE_LIMIT
    return max(0, limit - count)
