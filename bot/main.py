from __future__ import annotations

import logging
import os

from telebot import TeleBot

logger = logging.getLogger(__name__)


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")
    return TeleBot(token)


def run_bot() -> None:
    bot = build_bot()
    logger.info("Telegram bot starting")
    bot.infinity_polling(skip_pending=True)
