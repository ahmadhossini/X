from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic, time

from telebot import TeleBot
from telebot.types import ChatPermissions, Message

from ai.moderation import moderation_engine
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

    def _delete(self, message: Message) -> bool:
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
            return True
        except Exception:
            return False

    def _warn_user(self, message: Message, reason: str, count: int) -> None:
        """Send a concise automatic warning when a moderation rule is violated."""
        if not message.from_user:
            return
        try:
            name = message.from_user.first_name or "کاربر"
            self.bot.reply_to(
                message,
                f"{name}، این پیام به دلیل رعایت نکردن قوانین گروه حذف شد.\n"
                f"دلیل: {reason}\n"
                f"تعداد هشدارها: {count}",
            )
        except Exception:
            # The offending message may already be deleted or unavailable for
            # replying. Warning failure must never break moderation.
            try:
                self.bot.send_message(
                    message.chat.id,
                    f"کاربر {message.from_user.first_name or 'کاربر'} به دلیل «{reason}» هشدار گرفت.\n"
                    f"تعداد هشدارها: {count}",
                )
            except Exception:
                pass

    def handle(self, message: Message) -> bool:
        """Apply enabled group moderation rules to a user message.

        This method is intentionally called for both text and media messages by
        the bot dispatcher. Returning True means the message was handled by a
        moderation rule and should not continue into the AI pipeline.
        """
        if not message.from_user or self.is_admin(message):
            return False

        cfg = store.get(message.chat.id)
        text = message.text or message.caption or ""

        if cfg.forward_lock and getattr(message, "forward_date", None):
            count = self.warn(message.chat.id, message.from_user.id, "ارسال پیام فورواردی")
            self._warn_user(message, "ارسال پیام فورواردی", count)
            self._delete(message)
            return True

        key = (message.chat.id, message.from_user.id)
        now = monotonic()
        bucket = self._messages[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 10:
            bucket.popleft()

        if (cfg.anti_flood or cfg.anti_spam) and moderation_engine.looks_like_flood(len(bucket)):
            try:
                self.bot.restrict_chat_member(
                    message.chat.id,
                    message.from_user.id,
                    permissions=self._mute_permissions(),
                    until_date=int(time()) + 60,
                )
                count = self.warn(message.chat.id, message.from_user.id, "ارسال پیام‌های متوالی")
                self._warn_user(message, "ارسال پیام‌های متوالی", count)
                self._delete(message)
                return True
            except Exception:
                return False

        checks = [
            (cfg.anti_link, moderation_engine.contains_link, "ارسال لینک"),
            (cfg.mention_lock, moderation_engine.contains_mention, "ارسال یوزرنیم"),
            (cfg.hashtag_lock, moderation_engine.contains_hashtag, "ارسال هشتگ"),
            (cfg.phone_lock, moderation_engine.contains_phone, "شماره تلفن"),
            (cfg.profanity_filter, moderation_engine.contains_profanity, "الفاظ نامناسب"),
            (cfg.drug_filter, moderation_engine.contains_drug_content, "محتوای مواد مخدر"),
            (cfg.nsfw_filter, moderation_engine.contains_nsfw_content, "محتوای نامناسب"),
        ]

        for enabled, checker, reason in checks:
            if enabled and checker(text):
                count = self.warn(message.chat.id, message.from_user.id, reason)
                self._warn_user(message, reason, count)
                self._delete(message)
                return True

        return False

    def warn(self, chat_id: int, user_id: int, reason: str) -> int:
        key = (chat_id, user_id)
        self._warnings[key] += 1
        return self._warnings[key]

    @staticmethod
    def _mute_permissions() -> ChatPermissions:
        return ChatPermissions(can_send_messages=False)
