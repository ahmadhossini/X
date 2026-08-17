from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic, time

from telebot import TeleBot
from telebot.types import ChatPermissions, Message

from ai.moderation import moderation_engine, normalize
from backend.chat_registry import registry
from backend.chat_stats import stats
from bot.services.group_settings_store import GroupSettings, store


class GroupModeration:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self._messages: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self._recent_text: dict[tuple[int, int], deque[str]] = defaultdict(deque)
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
            registry.upsert(
                message.chat.id,
                message.chat.title or "Untitled",
                message.chat.type,
                getattr(message.chat, "username", None),
            )

    def _delete(self, message: Message) -> bool:
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
            stats.record_action(message.chat.id, "deleted")
            return True
        except Exception:
            return False

    def _warn_delete(self, message: Message, reason: str, cfg: GroupSettings) -> bool:
        if not self._delete(message):
            return False
        warnings = self.warn(message.chat.id, message.from_user.id, reason)
        if warnings >= cfg.warning_limit:
            try:
                self.bot.restrict_chat_member(
                    message.chat.id,
                    message.from_user.id,
                    permissions=self._mute_permissions(),
                    until_date=int(time()) + cfg.flood_mute_seconds,
                )
                stats.record_action(message.chat.id, "restricted")
            except Exception:
                pass
        return True

    @staticmethod
    def _is_forwarded(message: Message) -> bool:
        return any(
            getattr(message, name, None) is not None
            for name in (
                "forward_from",
                "forward_from_chat",
                "forward_sender_name",
                "forward_origin",
                "is_automatic_forward",
            )
        )

    @staticmethod
    def _media_reason(message: Message, cfg: GroupSettings) -> str | None:
        content_type = getattr(message, "content_type", "")
        mapping = {
            "photo": (cfg.photo_lock, "عکس"),
            "video": (cfg.video_lock, "ویدیو"),
            "document": (cfg.document_lock, "فایل"),
            "audio": (cfg.audio_lock, "صوت"),
            "voice": (cfg.voice_lock, "ویس"),
            "video_note": (cfg.video_note_lock, "ویدیو نوت"),
            "sticker": (cfg.sticker_lock, "استیکر"),
            "animation": (cfg.animation_lock, "GIF"),
            "poll": (cfg.poll_lock, "نظرسنجی"),
            "location": (cfg.location_lock, "موقعیت مکانی"),
            "contact": (cfg.contact_lock, "مخاطب"),
        }
        locked = mapping.get(content_type)
        return locked[1] if locked and locked[0] else None

    def _anti_spam(self, key: tuple[int, int], text: str, cfg: GroupSettings) -> bool:
        if not cfg.anti_spam or not text:
            return False
        normalized = normalize(text)
        recent = self._recent_text[key]
        recent.append(normalized)
        while len(recent) > max(cfg.repeat_message_limit, 3):
            recent.popleft()
        if not normalized:
            return False
        return recent.count(normalized) >= cfg.repeat_message_limit

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
        while bucket and now - bucket[0] > cfg.flood_window_seconds:
            bucket.popleft()

        media_reason = self._media_reason(message, cfg)
        checks = (
            (cfg.forward_lock and self._is_forwarded(message), "پیام فورواردی"),
            (cfg.anti_link and moderation_engine.contains_link(text), "ارسال لینک"),
            (cfg.mention_lock and moderation_engine.contains_mention(text), "یوزرنیم @"),
            (cfg.hashtag_lock and moderation_engine.contains_hashtag(text), "هشتگ #"),
            (cfg.phone_lock and moderation_engine.contains_phone(text), "شماره تلفن"),
            (cfg.profanity_filter and moderation_engine.contains_profanity(text), "الفاظ نامناسب"),
            (cfg.drug_filter and moderation_engine.contains_drug_content(text), "محتوای مواد مخدر"),
            (cfg.nsfw_filter and moderation_engine.contains_nsfw_content(text), "محتوای نامناسب"),
            (media_reason is not None, media_reason or ""),
            (self._anti_spam(key, text, cfg), "پیام تکراری / اسپم"),
        )
        for matched, reason in checks:
            if matched:
                return self._warn_delete(message, reason, cfg)

        if cfg.anti_flood and len(bucket) >= cfg.flood_messages:
            try:
                self.bot.restrict_chat_member(
                    message.chat.id,
                    message.from_user.id,
                    permissions=self._mute_permissions(),
                    until_date=int(time()) + cfg.flood_mute_seconds,
                )
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
