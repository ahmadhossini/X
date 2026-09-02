from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select
from telebot import TeleBot, types
from telebot.types import CallbackQuery, Message

from api.github_connect import create_connect_state
from bot.locales import t
from code_agent.agent import AgentError, execute_task
from code_agent.github_app import GitHubAppError, github_app_get
from core.config import settings
from database.models import GitHubInstallation, User
from database.session import SessionLocal

logger = logging.getLogger(__name__)


def _get_or_create_user(telegram_id: int) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            user = User(telegram_id=telegram_id, language="fa")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user


def _language(telegram_id: int) -> str:
    return _get_or_create_user(telegram_id).language


def _set_language(telegram_id: int, language: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            user = User(telegram_id=telegram_id, language=language)
            db.add(user)
        else:
            user.language = language
        db.commit()


def _installation(telegram_id: int) -> GitHubInstallation | None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            return None
        return db.scalar(select(GitHubInstallation).where(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True)).order_by(GitHubInstallation.updated_at.desc()))


def _connect_markup(telegram_id: int, language: str) -> types.InlineKeyboardMarkup:
    state = create_connect_state(telegram_id)
    if not settings.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL is not configured")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(t(language, "connect_button"), url=f"{settings.public_base_url}/github/connect?state={state}"))
    return markup


def _main_keyboard(language: str) -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("XAI Code Agent"),
        types.KeyboardButton(t(language, "connect_menu_button")),
        types.KeyboardButton(t(language, "repos_menu_button")),
        types.KeyboardButton(t(language, "task_menu_button")),
        types.KeyboardButton(t(language, "language_menu_button")),
        types.KeyboardButton(t(language, "disconnect_menu_button")),
    )
    return markup


def _set_bot_commands(bot: TeleBot) -> None:
    bot.set_my_commands([
        types.BotCommand("start", "Start XAI Code Agent"),
        types.BotCommand("connect", "Connect GitHub"),
        types.BotCommand("repos", "List accessible repositories"),
        types.BotCommand("task", "Create a code change and Draft PR"),
        types.BotCommand("language", "Change language"),
        types.BotCommand("disconnect", "Disconnect GitHub"),
        types.BotCommand("help", "Show help"),
    ])


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = TeleBot(token)
    _set_bot_commands(bot)

    @bot.message_handler(commands=["start"])
    def start(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        payload = (message.text or "").split(maxsplit=1)
        if len(payload) > 1 and payload[1] == "github_connected":
            installation = _installation(user_id)
            if installation:
                bot.reply_to(message, t(language, "github_connected", login=installation.github_login or "GitHub"), reply_markup=_main_keyboard(language))
                return
        bot.reply_to(message, t(language, "welcome"), reply_markup=_main_keyboard(language))
        bot.send_message(message.chat.id, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language))

    @bot.message_handler(commands=["help"])
    def help_command(message: Message) -> None:
        language = _language(message.from_user.id) if message.from_user else "fa"
        bot.reply_to(message, t(language, "help"), reply_markup=_main_keyboard(language))
        if message.from_user:
            bot.send_message(message.chat.id, t(language, "connect_button_hint"), reply_markup=_connect_markup(message.from_user.id, language))

    @bot.message_handler(commands=["language"])
    def language_command(message: Message) -> None:
        language = _language(message.from_user.id) if message.from_user else "fa"
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(t(language, "language_button_en"), callback_data="lang:en"),
            types.InlineKeyboardButton(t(language, "language_button_hi"), callback_data="lang:hi"),
            types.InlineKeyboardButton(t(language, "language_button_fa"), callback_data="lang:fa"),
        )
        bot.reply_to(message, t(language, "choose_language"), reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("lang:")))
    def language_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.data:
            return
        language = call.data.split(":", 1)[1]
        if language not in {"en", "hi", "fa"}:
            bot.answer_callback_query(call.id, "Invalid language")
            return
        _set_language(call.from_user.id, language)
        bot.answer_callback_query(call.id)
        names = {"en": "English", "hi": "हिन्दी", "fa": "فارسی"}
        bot.send_message(call.message.chat.id, t(language, "language_saved", language=names[language]), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["connect"])
    def connect_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(message.from_user.id, language))

    @bot.message_handler(commands=["disconnect"])
    def disconnect(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
            if not user:
                bot.reply_to(message, t(language, "github_not_connected"), reply_markup=_main_keyboard(language))
                return
            count = db.query(GitHubInstallation).filter(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True)).update({"active": False})
            db.commit()
        bot.reply_to(message, t(language, "github_disconnected") if count else t(language, "github_not_connected"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["repos"])
    def repositories(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        installation = _installation(message.from_user.id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(message.from_user.id, language))
            return
        try:
            data = asyncio.run(github_app_get("/installation/repositories?per_page=100", installation.installation_id))
            repos = data.get("repositories", [])
            if not repos:
                bot.reply_to(message, t(language, "repos_empty"), reply_markup=_main_keyboard(language))
                return
            lines = [f"• {repo.get('full_name')}" for repo in repos[:50] if repo.get("full_name")]
            bot.reply_to(message, t(language, "repos_title") + "\n\n" + "\n".join(lines), reply_markup=_main_keyboard(language))
        except GitHubAppError:
            logger.exception("Failed to list GitHub repositories")
            bot.reply_to(message, t(language, "github_error"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        installation = _installation(message.from_user.id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(message.from_user.id, language))
            return
        raw = message.text or ""
        payload = raw[len("/task"):].strip()
        if "|" not in payload:
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language))
            return
        repository, request = [part.strip() for part in payload.split("|", 1)]
        if repository.count("/") != 1 or len(request) < 3:
            bot.reply_to(message, t(language, "invalid_repo"), reply_markup=_main_keyboard(language))
            return
        bot.reply_to(message, t(language, "task_received"), reply_markup=_main_keyboard(language))
        try:
            result = asyncio.run(execute_task(settings.gemini_api_key, settings.gemini_model, repository, request, installation.installation_id, True))
            if result["status"] == "no_changes":
                bot.reply_to(message, t(language, "no_changes", summary=result["summary"][:1500]), reply_markup=_main_keyboard(language))
                return
            pr = result.get("pull_request", {})
            pr_text = f"\nPR: {pr['url']}" if pr.get("url") else ""
            files = "\n".join(f"• {p}" for p in result.get("changes", []))
            reply = t(language, "changes_ready", summary=result.get("summary", ""), files=files, commit=result.get("commit", "")[:12], pr=pr_text)
            bot.reply_to(message, reply[:4000], reply_markup=_main_keyboard(language))
        except (AgentError, GitHubAppError, RuntimeError):
            logger.exception("Agent task failed for repository=%s", repository)
            bot.reply_to(message, t(language, "task_failed"), reply_markup=_main_keyboard(language))

    @bot.message_handler(func=lambda message: bool(message.text))
    def menu_buttons(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        text = (message.text or "").strip()
        if text == "XAI Code Agent":
            bot.reply_to(message, t(language, "menu_home"), reply_markup=_main_keyboard(language))
        elif text == t(language, "connect_menu_button"):
            connect_command(message)
        elif text == t(language, "repos_menu_button"):
            repositories(message)
        elif text == t(language, "task_menu_button"):
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language))
        elif text == t(language, "language_menu_button"):
            language_command(message)
        elif text == t(language, "disconnect_menu_button"):
            disconnect(message)

    return bot


def run_bot() -> None:
    bot = build_bot()
    logger.info("Telegram bot starting")
    bot.infinity_polling(skip_pending=True)
