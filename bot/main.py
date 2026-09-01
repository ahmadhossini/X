from __future__ import annotations

import logging
import os
import threading

from telebot import TeleBot
from telebot.types import Message

from code_agent.agent import AgentError, execute_task
from code_agent.github_app import GitHubAppError
from core.config import settings

logger = logging.getLogger(__name__)


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")
    bot = TeleBot(token)

    @bot.message_handler(commands=["start"])
    def start(message: Message) -> None:
        bot.reply_to(message, "XAI Code Agent آماده است.\n\n/task owner/repo | درخواست تغییر کد")

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        raw = message.text or ""
        payload = raw[len("/task"):].strip()
        if "|" not in payload:
            bot.reply_to(message, "فرمت:\n/task owner/repo | درخواست تغییر")
            return
        repository, request = [part.strip() for part in payload.split("|", 1)]
        if repository.count("/") != 1 or len(request) < 3:
            bot.reply_to(message, "مخزن یا درخواست نامعتبر است.")
            return
        bot.reply_to(message, "درخواست دریافت شد. در حال تحلیل مخزن و ساخت تغییرات...")
        try:
            result = _run_task(repository, request)
            if result["status"] == "no_changes":
                bot.reply_to(message, "تغییری لازم تشخیص داده نشد.\n" + result["summary"][:1500])
                return
            pr = result.get("pull_request", {})
            reply = "تغییرات آماده شد.\n\n" + result.get("summary", "")
            reply += "\n\nفایل‌ها:\n" + "\n".join(f"• {p}" for p in result.get("changes", []))
            reply += f"\n\nCommit: {result.get('commit', '')[:12]}"
            if pr.get("url"):
                reply += f"\nPR: {pr['url']}"
            bot.reply_to(message, reply[:4000])
        except (AgentError, GitHubAppError, RuntimeError) as exc:
            logger.exception("Agent task failed")
            bot.reply_to(message, f"خطا: {exc}")

    return bot


def _run_task(repository: str, request: str) -> dict:
    import asyncio
    return asyncio.run(execute_task(settings.gemini_api_key, settings.gemini_model, repository, request, True))


def run_bot() -> None:
    bot = build_bot()
    logger.info("Telegram bot starting")
    bot.infinity_polling(skip_pending=True)
