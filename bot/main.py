from __future__ import annotations

import logging
import threading
from typing import Optional

from telebot import TeleBot
from telebot.types import Message

from bot.services.moderation import GroupModeration
from core.config import settings

logger = logging.getLogger(__name__)


def _target_from_reply(message: Message) -> Optional[int]:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    return None


def build_bot() -> TeleBot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = TeleBot(settings.bot_token, parse_mode="HTML")
    moderation = GroupModeration(bot)

    def is_admin(message: Message) -> bool:
        if message.chat.type not in {"group", "supergroup"}:
            return False
        try:
            member = bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {"creator", "administrator"}
        except Exception:
            return False

    @bot.message_handler(commands=["start", "help"])
    def start(message: Message):
        bot.reply_to(
            message,
            "<b>XAI MASTER V2</b>\n\n"
            "مدیر هوشمند گروه در حال اجراست.\n\n"
            "قابلیت‌های فعال:\n"
            "• Anti-Link\n• Anti-Flood\n• Warning\n• Mute / Unmute\n• Ban / Unban\n\n"
            "برای مدیریت طبیعی، پیام خود را در گروه به ربات بگویید.",
        )

    @bot.message_handler(commands=["market"])
    def market(message: Message):
        bot.reply_to(
            message,
            "مرکز بازار هنوز در حال تکمیل است. Mini App در مرحله بعد به ربات متصل می‌شود.",
        )

    @bot.message_handler(commands=["unmute", "رفع_محدودیت"])
    def unmute(message: Message):
        if not is_admin(message):
            return bot.reply_to(message, "فقط مدیران گروه می‌توانند این دستور را اجرا کنند.")
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "روی پیام کاربر ریپلای کنید و دوباره دستور را بفرستید.")
        try:
            bot.restrict_chat_member(
                message.chat.id,
                user_id,
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
            bot.reply_to(message, "محدودیت کاربر برداشته شد.")
        except Exception as exc:
            logger.exception("unmute failed: %s", exc)
            bot.reply_to(message, "نتوانستم محدودیت کاربر را بردارم. مطمئن شوید ربات دسترسی لازم را دارد.")

    @bot.message_handler(commands=["ban"])
    def ban(message: Message):
        if not is_admin(message):
            return bot.reply_to(message, "فقط مدیران گروه می‌توانند این دستور را اجرا کنند.")
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "روی پیام کاربر ریپلای کنید.")
        try:
            bot.ban_chat_member(message.chat.id, user_id)
            bot.reply_to(message, "کاربر مسدود شد.")
        except Exception:
            bot.reply_to(message, "نتوانستم کاربر را مسدود کنم. دسترسی Ban را بررسی کنید.")

    @bot.message_handler(commands=["unban"])
    def unban(message: Message):
        if not is_admin(message):
            return bot.reply_to(message, "فقط مدیران گروه می‌توانند این دستور را اجرا کنند.")
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "روی پیام کاربر ریپلای کنید.")
        try:
            bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
            bot.reply_to(message, "کاربر از مسدودی خارج شد.")
        except Exception:
            bot.reply_to(message, "نتوانستم مسدودی کاربر را بردارم.")

    @bot.message_handler(content_types=["text"])
    def moderate(message: Message):
        if message.chat.type in {"group", "supergroup"}:
            moderation.handle(message)

    return bot


def run_bot() -> None:
    bot = build_bot()
    logger.info("XAI MASTER V2 starting Telegram polling")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
