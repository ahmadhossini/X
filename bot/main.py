from __future__ import annotations

import asyncio
import logging
import os

from telebot import TeleBot
from telebot.types import Message

from code_agent.agent import AgentError, execute_task
from code_agent.github_app import GitHubAppError, github_app_get
from core.config import settings

logger = logging.getLogger(__name__)


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = TeleBot(token)

    def authorized(message: Message) -> bool:
        if not settings.telegram_admin_ids:
            bot.reply_to(message, "دسترسی مدیر تنظیم نشده است.")
            logger.warning("Rejected Telegram request because TELEGRAM_ADMIN_IDS is empty")
            return False
        if message.from_user and message.from_user.id in settings.telegram_admin_ids:
            return True
        bot.reply_to(message, "دسترسی به Code Agent برای این حساب فعال نیست.")
        logger.warning("Rejected Telegram user id=%s", getattr(message.from_user, "id", None))
        return False

    @bot.message_handler(commands=["start", "help"])
    def start(message: Message) -> None:
        bot.reply_to(
            message,
            "XAI Code Agent\n\n"
            "/repos — فهرست مخزن‌های قابل دسترسی\n"
            "/task owner/repo | درخواست تغییر کد\n\n"
            "هر تغییر در یک branch جدا ساخته و به صورت Draft PR ثبت می‌شود.",
        )

    @bot.message_handler(commands=["repos"])
    def repositories(message: Message) -> None:
        if not authorized(message):
            return
        try:
            data = asyncio.run(github_app_get("/installation/repositories?per_page=100"))
            repos = data.get("repositories", [])
            if not repos:
                bot.reply_to(message, "هیچ مخزن قابل دسترسی پیدا نشد.")
                return
            lines = [f"• {repo.get('full_name')}" for repo in repos[:50] if repo.get("full_name")]
            bot.reply_to(message, "مخزن‌های قابل دسترسی:\n\n" + "\n".join(lines))
        except GitHubAppError:
            logger.exception("Failed to list GitHub repositories")
            bot.reply_to(message, "خطا در دریافت فهرست مخزن‌ها.")

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        if not authorized(message):
            return
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
        except (AgentError, GitHubAppError, RuntimeError):
            logger.exception("Agent task failed for repository=%s", repository)
            bot.reply_to(message, "اجرای درخواست ناموفق بود. جزئیات خطا در لاگ سرور ثبت شد.")

    return bot


def _run_task(repository: str, request: str) -> dict:
    return asyncio.run(
        execute_task(settings.gemini_api_key, settings.gemini_model, repository, request, True)
    )


def run_bot() -> None:
    bot = build_bot()
    logger.info("Telegram bot starting")
    bot.infinity_polling(skip_pending=True)
