from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select
from telebot import TeleBot, types
from telebot.types import CallbackQuery, Message

from api.github_connect import create_connect_state
from billing.service import BillingError, ensure_user_credit_state, estimate_task_credits, reserve_task_credits
from bot.coding_advice import handle_coding_advice
from bot.locales import t
from code_agent.github_app import github_app_get
from core.config import settings
from database.models import GitHubInstallation, User
from database.session import SessionLocal

logger = logging.getLogger(__name__)
SUPPORTED_LANGUAGES = {"en", "hi", "fa"}
_PENDING_TASKS: dict[int, tuple[str, list[str]]] = {}


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _get_or_create_user(telegram_id: int) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
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
        if user is None:
            db.add(User(telegram_id=telegram_id, language=language))
        else:
            user.language = language
        db.commit()


def _installation(telegram_id: int) -> GitHubInstallation | None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return None
        return db.scalar(
            select(GitHubInstallation)
            .where(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True))
            .order_by(GitHubInstallation.updated_at.desc())
        )


def _connect_markup(telegram_id: int, language: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    try:
        state = create_connect_state(telegram_id)
        base_url = settings.public_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError("PUBLIC_BASE_URL is not configured")
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), url=f"{base_url}/github/connect?state={state}"))
    except Exception:
        logger.exception("Failed to create GitHub connect button")
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), callback_data="github:config_error"))
    return markup


def _language_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.row(
        types.InlineKeyboardButton("English", callback_data="lang:en"),
        types.InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
        types.InlineKeyboardButton("فارسی", callback_data="lang:fa"),
    )
    return markup


def _main_keyboard(language: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(t(language, "connect_menu_button"), callback_data="menu:connect"),
        types.InlineKeyboardButton(t(language, "repos_menu_button"), callback_data="menu:repos"),
    )
    markup.row(
        types.InlineKeyboardButton(t(language, "task_menu_button"), callback_data="menu:task"),
        types.InlineKeyboardButton(t(language, "coding_advice_button"), callback_data="menu:advice"),
    )
    markup.row(types.InlineKeyboardButton(t(language, "support_button"), callback_data="menu:support"))
    return markup


def _repo_selection_markup(repositories: list[str]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for index, repository in enumerate(repositories[:20]):
        label = repository.split("/", 1)[-1]
        if len(label) > 45:
            label = label[:42] + "..."
        markup.add(types.InlineKeyboardButton(label, callback_data=f"taskrepo:{index}"))
    return markup


def _set_user_commands(bot: TeleBot, user_id: int, language: str) -> None:
    descriptions = {
        "en": {"start": "Start XAI Code Agent", "connect": "Connect GitHub", "repos": "List repositories", "task": "Create a code change", "balance": "Show credits and plan", "language": "Change language", "disconnect": "Disconnect GitHub", "help": "Show help"},
        "hi": {"start": "XAI Code Agent शुरू करें", "connect": "GitHub कनेक्ट करें", "repos": "Repositories देखें", "task": "Code change बनाएँ", "balance": "क्रेडिट और प्लान देखें", "language": "भाषा बदलें", "disconnect": "GitHub से संबंध हटाएँ", "help": "मदद देखें"},
        "fa": {"start": "شروع XAI Code Agent", "connect": "اتصال GitHub", "repos": "نمایش مخزن‌ها", "task": "ایجاد تغییر کد", "balance": "نمایش اعتبار و پلن", "language": "تغییر زبان", "disconnect": "قطع اتصال GitHub", "help": "نمایش راهنما"},
    }
    d = descriptions.get(language, descriptions["en"])
    bot.set_my_commands([types.BotCommand(command, description) for command, description in d.items()], scope=types.BotCommandScopeChat(user_id))


def _queue_task(user_id: int, repository: str, request: str, installation: GitHubInstallation, chat_id: int, language: str, bot: TeleBot) -> None:
    estimated_credits = estimate_task_credits(request)
    try:
        reservation = reserve_task_credits(user_id, repository, request, estimated_credits, installation_id=installation.installation_id, model=settings.gemini_model, chat_id=chat_id, language=language)
    except BillingError as exc:
        if str(exc) == "Insufficient credits":
            try:
                credits, plan = ensure_user_credit_state(user_id)
            except BillingError:
                credits, plan = 0, "free"
            bot.send_message(chat_id, t(language, "insufficient_credits", credits=credits, required=estimated_credits, plan=plan), reply_markup=_main_keyboard(language))
        elif str(exc) == "Active task already exists":
            bot.send_message(chat_id, t(language, "task_already_running"), reply_markup=_main_keyboard(language))
        else:
            bot.send_message(chat_id, t(language, "billing_error"), reply_markup=_main_keyboard(language))
        return
    bot.send_message(chat_id, t(language, "task_received_with_cost", credits=estimated_credits, remaining=reservation.remaining), reply_markup=_main_keyboard(language))


def _send_repositories(bot: TeleBot, user_id: int, chat_id: int, language: str) -> None:
    installation = _installation(user_id)
    if not installation:
        bot.send_message(chat_id, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language))
        return
    try:
        data = _run_async(github_app_get, "/installation/repositories?per_page=100", installation.installation_id)
        repos = data.get("repositories", [])
        if not repos:
            bot.send_message(chat_id, t(language, "repos_empty"), reply_markup=_main_keyboard(language))
            return
        lines = [f"· {repo.get('full_name')}" for repo in repos[:50] if repo.get("full_name")]
        bot.send_message(chat_id, t(language, "repos_title") + "\n\n" + "\n".join(lines), reply_markup=_main_keyboard(language))
    except Exception:
        logger.exception("Failed to list repositories")
        bot.send_message(chat_id, t(language, "github_error"), reply_markup=_main_keyboard(language))


def build_bot() -> TeleBot:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")
    bot = TeleBot(token, num_threads=min(max(settings.code_agent_workers, 4), 12))

    @bot.message_handler(commands=["start"])
    def start(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        payload = (message.text or "").split(maxsplit=1)
        if not _language_selected(user_id):
            bot.reply_to(message, t("en", "choose_language"), reply_markup=_language_markup(), parse_mode="HTML")
            return
        language = _language(user_id)
        _set_user_commands(bot, user_id, language)
        if len(payload) > 1 and payload[1] == "connect_github":
            bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language), parse_mode="HTML")
            return
        if len(payload) > 1 and payload[1] == "github_connected":
            installation = _installation(user_id)
            if installation:
                bot.reply_to(message, t(language, "github_connected", login=installation.github_login or "GitHub"), reply_markup=_main_keyboard(language), parse_mode="HTML")
                return
        bot.reply_to(message, t(language, "welcome"), reply_markup=_main_keyboard(language), parse_mode="HTML")

    @bot.message_handler(commands=["help"])
    def help_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        bot.reply_to(message, t(language, "help"), reply_markup=_main_keyboard(language), parse_mode="HTML")

    @bot.message_handler(commands=["balance"])
    def balance_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        try:
            credits, plan = ensure_user_credit_state(message.from_user.id)
            bot.reply_to(message, t(language, "balance", credits=credits, plan=plan), reply_markup=_main_keyboard(language), parse_mode="HTML")
        except BillingError:
            bot.reply_to(message, t(language, "billing_error"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["language"])
    def language_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
        bot.reply_to(message, t(language, "choose_language"), reply_markup=_language_markup(), parse_mode="HTML")

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("menu:")))
    def menu_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.message or not call.data:
            return
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        language = _language(user_id)
        action = call.data.split(":", 1)[1]
        bot.answer_callback_query(call.id)
        if action == "connect":
            bot.send_message(chat_id, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language), parse_mode="HTML")
        elif action == "repos":
            _send_repositories(bot, user_id, chat_id, language)
        elif action == "task":
            bot.send_message(chat_id, t(language, "task_format"), reply_markup=_main_keyboard(language), parse_mode="HTML")
        elif action == "advice":
            bot.send_message(chat_id, t(language, "chat_prompt"), reply_markup=_main_keyboard(language), parse_mode="HTML")
        elif action == "support":
            bot.send_message(chat_id, t(language, "support_text"), reply_markup=_main_keyboard(language), parse_mode="HTML")

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("taskrepo:")))
    def task_repository_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.message or not call.data:
            return
        user_id = call.from_user.id
        language = _language(user_id)
        pending = _PENDING_TASKS.get(user_id)
        if not pending:
            bot.answer_callback_query(call.id, t(language, "task_format"), show_alert=True)
            return
        try:
            index = int(call.data.split(":", 1)[1])
            request, repositories = pending
            repository = repositories[index]
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, t(language, "github_error"), show_alert=True)
            return
        _PENDING_TASKS.pop(user_id, None)
        installation = _installation(user_id)
        if not installation:
            bot.answer_callback_query(call.id, t(language, "connect_first"), show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"Repository: {repository}\n\n{t(language, 'task_received')}", parse_mode="HTML")
        _queue_task(user_id, repository, request, installation, call.message.chat.id, language, bot)

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("lang:")))
    def language_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.data:
            return
        language = call.data.split(":", 1)[1]
        if language not in SUPPORTED_LANGUAGES:
            bot.answer_callback_query(call.id, t("en", "github_error"))
            return
        try:
            _set_language(call.from_user.id, language)
            _set_user_commands(bot, call.from_user.id, language)
            bot.answer_callback_query(call.id, t(language, "language_selected"))
            if call.message:
                bot.send_message(call.message.chat.id, t(language, "welcome"), reply_markup=_main_keyboard(language), parse_mode="HTML")
        except Exception:
            logger.exception("Language selection failed")
            bot.answer_callback_query(call.id, t(language, "github_error"), show_alert=True)

    @bot.callback_query_handler(func=lambda call: bool(call.data == "github:config_error"))
    def github_config_error(call: CallbackQuery) -> None:
        language = _language(call.from_user.id) if call.from_user else "en"
        bot.answer_callback_query(call.id, t(language, "github_config_error"), show_alert=True)

    @bot.message_handler(commands=["connect"])
    def connect_command(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language), parse_mode="HTML")

    @bot.message_handler(commands=["disconnect"])
    def disconnect(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.telegram_id == user_id))
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
        user_id = message.from_user.id
        language = _language(user_id)
        _send_repositories(bot, user_id, message.chat.id, language)

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        installation = _installation(user_id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language), parse_mode="HTML")
            return
        request = (message.text or "")[len("/task"):].strip()
        if len(request) < 3 or request.startswith("/"):
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language), parse_mode="HTML")
            return
        try:
            data = _run_async(github_app_get, "/installation/repositories?per_page=100", installation.installation_id)
            repositories = [repo.get("full_name") for repo in data.get("repositories", []) if repo.get("full_name")]
        except Exception:
            logger.exception("Failed to resolve repository for task")
            bot.reply_to(message, t(language, "github_error"), reply_markup=_main_keyboard(language))
            return
        if not repositories:
            bot.reply_to(message, t(language, "repos_empty"), reply_markup=_main_keyboard(language))
            return
        if len(repositories) > 1:
            _PENDING_TASKS[user_id] = (request, repositories)
            bot.reply_to(message, t(language, "task_choose_repo", count=len(repositories)), reply_markup=_repo_selection_markup(repositories), parse_mode="HTML")
            return
        _queue_task(user_id, repositories[0], request, installation, message.chat.id, language, bot)

    @bot.message_handler(func=lambda message: bool(message.text))
    def text_handler(message: Message) -> None:
        if not message.from_user:
            return
        text_value = (message.text or "").strip()
        if text_value and not text_value.startswith("/"):
            handle_coding_advice(bot, message)

    return bot
