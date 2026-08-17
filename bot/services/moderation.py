from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic, time

from telebot import TeleBot
from telebot.types import ChatPermissions, Message

from ai.moderation import moderation_engine
from backend.chat_registry import registry
from backend.chat_stats import stats
from bot.services.group_settings_store import store


class GroupModeration:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self._messages: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._warnings: dict[tuple[int, int], int] = defaultdict(int)

    def is_admin(self, message: Message) -> bool:
        if not message.from_user:
            return True
        try:
            member = self.bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {"administrator", "creator"}
        except Exception:
            return False

    def _register_chat(self, message: Message) -> None:
        if message.chat.type in {"group", "supergroup", "channel"}:
            registry.upsert(message.chat.id, message.chat.title or "Untitled", message.chat.type, getattr(message.chat, "username", None))

    def _delete(self, message: Message) -> bool:
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
            stats.record_action(message.chat.id, "deleted")
            return True
        except Exception:
            return False

    def _warn_delete(self, message: Message, reason: str) -> bool:
        if self._delete(message):
            self.warn(message.chat.id, message.from_user.id, reason)
            return True
        return False

    def _is_forwarded(self, message: Message) -> bool:
        return any(
            getattr(message, name, None) is not None
            for name in ("forward_from", "forward_from_chat", "forward_sender_name", "forward_origin", "is_automatic_forward")
        )

    def handle(self, message: Message) -> bool:
        self._register_chat(message)
        if not message.from_user or self.is_admin(message):
            return False
        stats.record_message(message.chat.id, message.from_user.id)
        cfg = store.get(message.chat.id)
        text = message.text or message.caption or ""
        key = (message.chat.id, message.from_user.id)
        now = monotonic()
        bucket = self._messages[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 10:
            bucket.popleft()

        checks = (
            (cfg.forward_lock and self._is_forwarded(message), "پیام فورواردی"),
            (cfg.anti_link and moderation_engine.contains_link(text), "ارسال لینک"),
            (cfg.mention_lock and moderation_engine.contains_mention(text), "یوزرنیم @"),
            (cfg.hashtag_lock and moderation_engine.contains_hashtag(text), "هشتگ #"),
            (cfg.phone_lock and moderation_engine.contains_phone(text), "شماره تلفن"),
            (cfg.profanity_filter and moderation_engine.contains_profanity(text), "الفاظ نامناسب"),
            (cfg.drug_filter and moderation_engine.contains_drug_content(text), "محتوای مواد مخدر"),
            (cfg.nsfw_filter and moderation_engine.contains_nsfw_content(text), "محتوای جنسی"),
        )
        for matched, reason in checks:
            if matched:
                return self._warn_delete(message, reason)

        if cfg.anti_flood and moderation_engine.looks_like_flood(len(bucket)):
            try:
                self.bot.restrict_chat_member(message.chat.id, message.from_user.id, permissions=self._mute_permissions(), until_date=int(time()) + 60)
                self.warn(message.chat.id, message.from_user.id, "ارسال پیام‌های متوالی")
                stats.record_action(message.chat.id, "restricted")
                return True
            except Exception:
                return False
        return False

    def warn(self, chat_id: int, user_id: int, reason: str) -> int:
        key = (chat_id, user_id)
        self._warnings[key] += 1
        stats.record_action(chat_id, "warnings")
        return self._warnings[key]

    @staticmethod
    def _mute_permissions() -> ChatPermissions:
        return ChatPermissions(can_send_messages=False)
