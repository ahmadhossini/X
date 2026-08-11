from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from telebot import TeleBot
from telebot.types import Message

from ai.moderation import moderation_engine


class GroupModeration:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self._messages: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._warnings: dict[tuple[int, int], int] = defaultdict(int)

    def is_admin(self, message: Message) -> bool:
        try:
            member = self.bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {"administrator", "creator"}
        except Exception:
            return False

    def handle(self, message: Message) -> bool:
        if not message.text or self.is_admin(message):
            return False

        key = (message.chat.id, message.from_user.id)
        now = monotonic()
        bucket = self._messages[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 10:
            bucket.popleft()

        if moderation_engine.contains_link(message.text):
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
                self.warn(message.chat.id, message.from_user.id, "ارسال لینک")
                return True
            except Exception:
                return False

        if len(bucket) >= 8:
            try:
                self.bot.restrict_chat_member(
                    message.chat.id,
                    message.from_user.id,
                    permissions=self._mute_permissions(),
                    until_date=int(now + 60),
                )
                return True
            except Exception:
                return False
        return False

    def warn(self, chat_id: int, user_id: int, reason: str) -> int:
        key = (chat_id, user_id)
        self._warnings[key] += 1
        return self._warnings[key]

    @staticmethod
    def _mute_permissions():
        from telebot.types import ChatPermissions

        return ChatPermissions(can_send_messages=False)
