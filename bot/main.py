from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

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

SUPPORTED_LANGUAGES = {"en", "hi", "fa"}

background_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=settings.code_agent_workers,
    thread_name_prefix="xai-worker",
)
_task_slots = threading.BoundedSemaphore(
    settings.code_agent_workers + settings.code_agent_queue_size
)
_user_tasks: set[int] = set()
_user_tasks_lock = threading.Lock()

_BUSY_TEXT = {
    "en": "The task queue is busy. Please try again shortly.",
    "hi": "कार्य कतार व्यस्त है। कृपया थोड़ी देर बाद फिर प्रयास करें।",
    "fa": "صف پردازش شلوغ است. لطفاً کمی بعد دوباره تلاش کنید.",
}
_ALREADY_RUNNING_TEXT = {
    "en": "You already have a task running. Please wait for it to finish.",
    "hi": "आपका एक कार्य पहले से चल रहा है। कृपया उसके समाप्त होने तक प्रतीक्षा करें।",
    "fa": "یک کار برای شما در حال اجراست. لطفاً تا پایان آن صبر کنید.",
}


def _run_async_in_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args, **kwargs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _submit_background(user_id: int, func: Callable[..., Any], *args: Any) -> bool:
    """Submit a bounded background job and enforce one expensive job per user."""
    if not _task_slots.acquire(blocking=False):
        return False

    with _user_tasks_lock:
        if user_id in _user_tasks:
            _task_slots.release()
            return False
        _user_tasks.add(user_id)

    try:
        future = background_executor.submit(func, *args)
    except Exception:
        with _user_tasks_lock:
            _user_tasks.discard(user_id)
        _task_slots.release()
        raise

    def _done(_future: concurrent.futures.Future[Any]) -> None:
        with _user_tasks_lock:
            _user_tasks.discard(user_id)
        _task_slots.release()
        try:
            _future.exception()
        except concurrent.futures.CancelledError:
            pass
        except Exception:
            logger.exception("Background task callback failed for telegram_id=%s", user_id)

    future.add_done_callback(_done)
    return True


def _get_or_create_user(telegram_id: int) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            user = User(telegram_id=telegram_id, language="unset")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user


def _language(telegram_id: int) -> str:
    language = _get_or_create_user(telegram_id).language
    return language if language in SUPPORTED_LANGUAGES else "en"


def _language_selected(telegram_id: int) -> bool:
    return _get_or_create_user(telegram_id).language in SUPPORTED_LANGUAGES


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
        return db.scalar(
            select(GitHubInstallation)
            .where(
                GitHubInstallation.user_id == user.id,
                GitHubInstallation.active.is_(True),
            )
            .order_by(GitHubInstallation.updated_at.desc())
        )


def _connect_markup(telegram_id: int, language: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    try:
        state = create_connect_state(telegram_id)
        base_url = settings.public_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError("PUBLIC_BASE_URL is not configured")
        url = f"{base_url}/github/connect?state={state}"
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), url=url))
    except Exception:
        logger.exception("Failed to create GitHub connect button for telegram_id=%s", telegram_id)
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), callback_data="github:config_error"))
    return markup


def _main_keyboard(language: str) -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton(t(language, "brand_button")),
        types.KeyboardButton(t(language, "connect_menu_button")),
        types.KeyboardButton(t(language, "repos_menu_button")),
        types.KeyboardButton(t(language, "task_menu_button")),
        types.KeyboardButton(t(language, "language_menu_button")),
        types.KeyboardButton(t(language, "disconnect_menu_button")),
    )
    return markup


def _language_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("English", callback_data="lang:en"),
        types.InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
        types.InlineKeyboardButton("فارسی", callback_data="lang:fa"),
    )
    return markup


def _set_user_commands(bot: TeleBot, user_id: int, language: str) -> None:
    descriptions = {
        "en": {
            "start": "Start XAI Code Agent", "connect": "Connect GitHub", "repos": "List repositories",
            "task": "Create a code change", "language": "Change language", "disconnect": "Disconnect GitHub", "help": "Show help",
        },
        "hi": {
            "start": "XAI Code Agent शुरू करें", "connect": "GitHub कनेक्ट करें", "repos": "Repositories देखें",
            "task": "Code change बनाएँ", "language": "भाषा बदलें", "disconnect": "GitHub डिस्कनेक्ट करें", "help": "मदद देखें",
        },
        "fa": {
            "start": "شروع XAI Code Agent", "connect": "اتصال GitHub", "repos": "نمایش مخزن‌ها",
            "task": "ایجاد تغییر کد", "language": "تغییر زبان", "disconnect": "قطع اتصال GitHub", "help": "نمایش راهنما",
        },
    }
    d = descriptions.get(language, descriptions["en"])
    bot.set_my_commands(
        [types.BotCommand(command, description) for command, description in d.items()],
        scope=types.BotCommandScopeChat(user_id),
    )


def _language_prompt() -> str:
    return "Choose your language / अपनी भाषा चुनें / زبان خود را انتخاب کنید:"


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = TeleBot(token)

    @bot.message_handler(commands=["start"])
    def start(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        payload = (message.text or "").split(maxsplit=1)
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        _set_user_commands(bot, user_id, language)
        if len(payload) > 1 and payload[1] == "connect_github":
            bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language))
            return
        if len(payload) > 1 and payload[1] == "github_connected":
            installation = _installation(user_id)
            if installation:
                bot.reply_to(
                    message,
                    t(language, "github_connected", login=installation.github_login or "GitHub"),
                    reply_markup=_main_keyboard(language),
                )
                return
        bot.reply_to(message, t(language, "welcome"), reply_markup=_main_keyboard(language), parse_mode="HTML")

    @bot.message_handler(commands=["help"])
    def help_command(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        bot.reply_to(message, t(language, "help"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["language"])
    def language_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id) if _language_selected(message.from_user.id) else "en"
        bot.reply_to(message, t(language, "choose_language"), reply_markup=_language_markup())

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("lang:")))
    def language_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.data:
            return
        language = call.data.split(":", 1)[1]
        if language not in SUPPORTED_LANGUAGES:
            bot.answer_callback_query(call.id, "Invalid language")
            return
        try:
            _set_language(call.from_user.id, language)
            _set_user_commands(bot, call.from_user.id, language)
            bot.answer_callback_query(call.id, t(language, "language_selected"))
            if call.message:
                try:
                    bot.edit_message_text(
                        t(language, "language_selected") + "\n\n" + t(language, "welcome"),
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        parse_mode="HTML",
                    )
                except Exception:
                    logger.exception("Failed to edit language selection message")
                bot.send_message(
                    call.message.chat.id,
                    t(language, "menu_home"),
                    reply_markup=_main_keyboard(language),
                    parse_mode="HTML",
                )
        except Exception:
            logger.exception("Language selection failed for telegram_id=%s", call.from_user.id)
            try:
                bot.answer_callback_query(call.id, "Language selection failed. Please try again.", show_alert=True)
            except Exception:
                pass

    @bot.callback_query_handler(func=lambda call: bool(call.data == "github:config_error"))
    def github_config_error(call: CallbackQuery) -> None:
        language = _language(call.from_user.id) if call.from_user else "en"
        bot.answer_callback_query(call.id, t(language, "github_config_error"), show_alert=True)

    @bot.message_handler(commands=["connect"])
    def connect_command(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language))

    @bot.message_handler(commands=["disconnect"])
    def disconnect(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.telegram_id == user_id))
            if not user:
                bot.reply_to(message, t(language, "github_not_connected"), reply_markup=_main_keyboard(language))
                return
            count = db.query(GitHubInstallation).filter(
                GitHubInstallation.user_id == user.id,
                GitHubInstallation.active.is_(True),
            ).update({"active": False})
            db.commit()
        bot.reply_to(
            message,
            t(language, "github_disconnected") if count else t(language, "github_not_connected"),
            reply_markup=_main_keyboard(language),
        )

    @bot.message_handler(commands=["repos"])
    def repositories(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        installation = _installation(user_id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language))
            return

        def _fetch_repos_and_reply(chat_id: int, telegram_id: int, installation_id: int, lang: str) -> None:
            try:
                data = _run_async_in_thread(
                    github_app_get, "/installation/repositories?per_page=100", installation_id
                )
                repos = data.get("repositories", [])
                if not repos:
                    bot.send_message(chat_id, t(lang, "repos_empty"), reply_markup=_main_keyboard(lang))
                    return
                lines = [f"• {repo.get('full_name')}" for repo in repos[:50] if repo.get("full_name")]
                bot.send_message(
                    chat_id,
                    t(lang, "repos_title") + "\n\n" + "\n".join(lines),
                    reply_markup=_main_keyboard(lang),
                )
            except Exception:
                logger.exception("Failed to list GitHub repositories for telegram_id=%s", telegram_id)
                bot.send_message(chat_id, t(lang, "github_error"), reply_markup=_main_keyboard(lang))

        if not _submit_background(user_id, _fetch_repos_and_reply, message.chat.id, user_id, installation.installation_id, language):
            bot.reply_to(message, _ALREADY_RUNNING_TEXT[language], reply_markup=_main_keyboard(language))
            return
        bot.reply_to(message, t(language, "task_received"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        installation = _installation(user_id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language))
            return

        raw = message.text or ""
        payload = raw[len("/task"):].strip()
        if "|" not in payload:
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language))
            return
        repository, request = [part.strip() for part in payload.split("|", 1)]
        if repository.count("/") != 1 or any(part in repository for part in ("..", " ")) or len(request) < 3:
            bot.reply_to(message, t(language, "invalid_repo"), reply_markup=_main_keyboard(language))
            return

        def _run_task_and_reply(chat_id: int, api_key: str, model: str, repo: str, req: str, installation_id: int, lang: str) -> None:
            try:
                result = _run_async_in_thread(execute_task, api_key, model, repo, req, installation_id, True)
                if result["status"] == "no_changes":
                    bot.send_message(
                        chat_id,
                        t(lang, "no_changes", summary=result["summary"][:1500]),
                        reply_markup=_main_keyboard(lang),
                    )
                    return
                pr = result.get("pull_request", {})
                pr_text = f"\nPR: {pr['url']}" if pr.get("url") else ""
                files = "\n".join(f"• {p}" for p in result.get("changes", []))
                reply = t(
                    lang,
                    "changes_ready",
                    summary=result.get("summary", ""),
                    files=files,
                    commit=result.get("commit", "")[:12],
                    pr=pr_text,
                )
                bot.send_message(chat_id, reply[:4000], reply_markup=_main_keyboard(lang))
            except (AgentError, GitHubAppError, RuntimeError):
                logger.exception("Agent task failed for repository=%s", repo)
                bot.send_message(chat_id, t(lang, "task_failed"), reply_markup=_main_keyboard(lang))
            except Exception:
                logger.exception("Unexpected error running task for repository=%s", repo)
                bot.send_message(chat_id, t(lang, "task_failed"), reply_markup=_main_keyboard(lang))

        if not _submit_background(
            user_id,
            _run_task_and_reply,
            message.chat.id,
            settings.gemini_api_key,
            settings.gemini_model,
            repository,
            request,
            installation.installation_id,
            language,
        ):
            with _user_tasks_lock:
                already_running = user_id in _user_tasks
            text = _ALREADY_RUNNING_TEXT[language] if already_running else _BUSY_TEXT[language]
            bot.reply_to(message, text, reply_markup=_main_keyboard(language))
            return

        bot.reply_to(message, t(language, "task_received"), reply_markup=_main_keyboard(language))

    @bot.message_handler(func=lambda message: bool(message.text))
    def menu_buttons(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not _language_selected(user_id):
            bot.reply_to(message, _language_prompt(), reply_markup=_language_markup())
            return
        language = _language(user_id)
        text = (message.text or "").strip()
        if text == t(language, "connect_menu_button"):
            bot.send_message(message.chat.id, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language))
        elif text == t(language, "repos_menu_button"):
            repositories(message)
        elif text == t(language, "task_menu_button"):
            bot.send_message(message.chat.id, t(language, "task_format"), reply_markup=_main_keyboard(language))
        elif text == t(language, "language_menu_button"):
            language_command(message)
        elif text == t(language, "disconnect_menu_button"):
            disconnect(message)
        elif text == t(language, "brand_button"):
            bot.send_message(message.chat.id, t(language, "menu_home"), reply_markup=_main_keyboard(language), parse_mode="HTML")

    return bot
