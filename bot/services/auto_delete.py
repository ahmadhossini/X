from __future__ import annotations

import re
import threading
from collections import defaultdict, deque
from typing import Deque, Dict

from telebot import TeleBot
from telebot.types import Message


class AutoDeleteManager:
    """Per-group timed deletion of user messages plus manual cleanup helpers."""

    def __init__(self, bot: TeleBot, max_recent: int = 500):
        self.bot = bot
        self.max_recent = max_recent
        self._delay: Dict[int, int] = {}
        self._recent: Dict[int, Deque[int]] = defaultdict(lambda: deque(maxlen=max_recent))
        self._lock = threading.Lock()

    @staticmethod
    def parse_duration(value: str) -> int:
        raw = value.strip().lower()
        if raw in {"off", "0", "خاموش", "غیرفعال"}:
            return 0
        match = re.fullmatch(
            r"(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|ثانیه|دقیقه|ساعت|روز)",
            raw,
        )
        if not match:
            raise ValueError("invalid duration")
        amount = int(match.group(1))
        unit = match.group(2)
        factors = {
            "s": 1, "sec": 1, "secs": 1, "ثانیه": 1,
            "m": 60, "min": 60, "mins": 60, "دقیقه": 60,
            "h": 3600, "hr": 3600, "hrs": 3600, "ساعت": 3600,
            "d": 86400, "day": 86400, "days": 86400, "روز": 86400,
        }
        seconds = amount * factors[unit]
        if seconds < 5 or seconds > 7 * 86400:
            raise ValueError("duration must be between 5 seconds and 7 days")
        return seconds

    def set_delay(self, chat_id: int, value: str) -> int:
        seconds = self.parse_duration(value)
        with self._lock:
            if seconds:
                self._delay[chat_id] = seconds
            else:
                self._delay.pop(chat_id, None)
        return seconds

    def get_delay(self, chat_id: int) -> int:
        with self._lock:
            return self._delay.get(chat_id, 0)

    def track(self, message: Message) -> None:
        if message.chat.type not in {"group", "supergroup"}:
            return
        with self._lock:
            self._recent[message.chat.id].append(message.message_id)

    def schedule(self, message: Message) -> None:
        if message.chat.type not in {"group", "supergroup"}:
            return
        self.track(message)
        delay = self.get_delay(message.chat.id)
        if not delay or getattr(message.from_user, "is_bot", False):
            return
        timer = threading.Timer(delay, self._delete, args=(message.chat.id, message.message_id))
        timer.daemon = True
        timer.start()

    def _delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def delete_reply(self, message: Message) -> bool:
        target = message.reply_to_message
        if not target:
            return False
        try:
            self.bot.delete_message(message.chat.id, target.message_id)
            self.bot.delete_message(message.chat.id, message.message_id)
            return True
        except Exception:
            return False

    def delete_recent(self, chat_id: int, count: int) -> int:
        count = max(1, min(count, 100))
        with self._lock:
            ids = list(self._recent.get(chat_id, ()))
            ids = ids[-count:]
        deleted = 0
        for message_id in reversed(ids):
            try:
                self.bot.delete_message(chat_id, message_id)
                deleted += 1
            except Exception:
                pass
        return deleted
