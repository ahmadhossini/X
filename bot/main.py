from __future__ import annotations

import threading

from telebot import TeleBot

from api.main import app
from bot.services.moderation import GroupModeration
from core.config import settings


def build_bot() -> TeleBot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    bot = TeleBot(settings.bot_token, parse_mode="HTML")
    moderation = GroupModeration(bot)

    @bot.message_handler(commands=["start", "help"])
    def start(message):
        bot.reply_to(
            message,
            "<b>XAI MASTER</b>\n\nمدیریت هوشمند گروه، دستیار AI و مرکز بازار در حال توسعه است.\n\n"
            "در گروه، من را به عنوان ادمین اضافه کنید تا قابلیت‌های مدیریت فعال شوند.",
        )

    @bot.message_handler(commands=["market"])
    def market(message):
        bot.reply_to(message, "برای مشاهده بازار، Mini App در نسخه بعدی فعال می‌شود.")

    @bot.message_handler(content_types=["text"])
    def moderate(message):
        if message.chat.type in {"group", "supergroup"}:
            moderation.handle(message)

    return bot


def run_bot() -> None:
    build_bot().infinity_polling(skip_pending=True)


if __name__ == "__main__":
    run_bot()
