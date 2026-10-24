from __future__ import annotations

import asyncio
import logging
import os
import re

from sqlalchemy import select
from telebot import TeleBot, types
from telebot.types import CallbackQuery, Message

from api.github_connect import create_connect_state
from app.workers.queue import enqueue_coding_task
from billing.service import BillingError, ensure_user_credit_state, estimate_task_credits, reserve_task_credits
from app.billing.stars import StarsPaymentError, confirm_stars_payment, validate_stars_precheckout
from bot.locales import t
from code_agent.github_app import github_app_get
from core.config import settings
from bot.telegram_polling_lock import TelegramPollingLock
from database.models import GitHubInstallation, User
from database.session import SessionLocal

logger = logging.getLogger(__name__)
SUPPORTED_LANGUAGES = {"en", "hi", "fa"}
TASK_REPO_REQUEST_RE = re.compile(r"^(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s*\|\s*(?P<request>.+)$", re.DOTALL)


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
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), url=f"{base_url}/github/connect?state={state}"))
    except Exception:
        logger.exception("Failed to create GitHub connect button")
        markup.add(types.InlineKeyboardButton(t(language, "connect_button"), callback_data="github:config_error"))
    return markup


def _language_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("English", callback_data="lang:en"),
        types.InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
        types.InlineKeyboardButton("فارسی", callback_data="lang:fa"),
    )
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


def _set_user_commands(bot: TeleBot, user_id: int, language: str) -> None:
    descriptions = {
        "en": {"start": "Start XAI Code Agent", "connect": "Connect GitHub", "repos": "List repositories", "task": "Create a code change", "balance": "Show credits and plan", "language": "Change language", "disconnect": "Disconnect GitHub", "help": "Show help"},
        "hi": {"start": "XAI Code Agent शुरू करें", "connect": "GitHub कनेक्ट करें", "repos": "Repositories देखें", "task": "Code change बनाएँ", "balance": "क्रेडिट और प्लान देखें", "language": "भाषा बदलें", "disconnect": "GitHub डिस्कनेक्ट करें", "help": "मदद देखें"},
        "fa": {"start": "شروع XAI Code Agent", "connect": "اتصال GitHub", "repos": "نمایش مخزن‌ها", "task": "ایجاد تغییر کد", "balance": "نمایش اعتبار و پلن", "language": "تغییر زبان", "disconnect": "قطع اتصال GitHub", "help": "نمایش راهنما"},
    }
    d = descriptions.get(language, descriptions["en"])
    bot.set_my_commands([types.BotCommand(command, description) for command, description in d.items()], scope=types.BotCommandScopeChat(user_id))


def _language_prompt() -> str:
    return "Choose your language / अपनी भाषा चुनें / زبان خود را انتخاب کنید:"


def _safe_enqueue_reason(error: Exception, language: str) -> str:
    """Return a useful enqueue diagnostic without leaking credentials or connection URLs."""
    raw = f"{type(error).__name__}: {error}".strip()
    folded = raw.casefold()

    if "redis_url is required" in folded:
        reason = {
            "fa": "تنظیم REDIS_URL در محیط سرور خالی یا تنظیم نشده است.",
            "hi": "सर्वर पर REDIS_URL सेट नहीं है या खाली है।",
            "en": "The REDIS_URL environment setting is missing or empty.",
        }
    elif any(term in folded for term in ("authentication required", "invalid password", "wrongpass", "noauth", "redis authentication")):
        reason = {
            "fa": "Redis اتصال را به‌دلیل نامعتبر بودن اطلاعات احراز هویت رد کرد.",
            "hi": "Redis ने गलत प्रमाणीकरण विवरण के कारण कनेक्शन अस्वीकार किया।",
            "en": "Redis rejected the connection because authentication failed.",
        }
    elif any(term in folded for term in ("connection refused", "actively refused")):
        reason = {
            "fa": "اتصال به میزبان Redis رد شد؛ سرویس یا میزبان/پورت تنظیم‌شده در دسترس نیست.",
            "hi": "Redis कनेक्शन अस्वीकार हुआ; सेवा या कॉन्फ़िगर किया गया host/port उपलब्ध नहीं है।",
            "en": "The Redis connection was refused; the service or configured host/port is unavailable.",
        }
    elif any(term in folded for term in ("timed out", "timeout")):
        reason = {
            "fa": "اتصال یا عملیات صف Redis به پایان مهلت انتظار رسید.",
            "hi": "Redis कनेक्शन या queue operation का समय समाप्त हो गया।",
            "en": "The Redis connection or queue operation timed out.",
        }
    elif any(term in folded for term in ("name or service not known", "temporary failure in name resolution", "getaddrinfo failed", "nodename nor servname", "name resolution")):
        reason = {
            "fa": "نام میزبان Redis از طریق DNS پیدا نشد؛ آدرس میزبان تنظیم‌شده را بررسی کن.",
            "hi": "DNS Redis host को नहीं खोज पाया; कॉन्फ़िगर किया गया host जाँचें।",
            "en": "DNS could not resolve the Redis host; check the configured hostname.",
        }
    elif any(term in folded for term in ("connection reset", "connection closed", "broken pipe", "server closed the connection")):
        reason = {
            "fa": "اتصال Redis هنگام ارسال وظیفه قطع شد؛ سرور Redis یا مسیر شبکه ارتباط را بست.",
            "hi": "कार्य भेजते समय Redis कनेक्शन टूट गया; Redis server या network ने कनेक्शन बंद किया।",
            "en": "The Redis connection dropped while submitting the job; the server or network closed it.",
        }
    else:
        # Preserve the actual exception class/message where safe, rather than
        # incorrectly claiming that the worker itself is offline.
        safe = raw
        safe = re.sub(r"(?i)(redis(?:s)?://)[^\s'\"]+", r"\1[credentials-redacted]", safe)
        safe = re.sub(r"(?i)(postgres(?:ql)?://)[^\s'\"]+", r"\1[credentials-redacted]", safe)
        safe = re.sub(r"(?i)(token|secret|password|api[_ -]?key|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", safe)
        safe = re.sub(r"(?i)bearer\s+[^\s]+", "Bearer [redacted]", safe)
        safe = re.sub(r"(?i)(://[^:/\s]+:)[^@/\s]+@", r"\1[redacted]@", safe)
        reason = {
            "fa": f"ثبت وظیفه در صف شکست خورد؛ جزئیات خطا: {safe[:350]}",
            "hi": f"कार्य को queue में भेजना विफल हुआ; त्रुटि विवरण: {safe[:350]}",
            "en": f"Submitting the task to the queue failed; error details: {safe[:350]}",
        }

    return reason.get(language, reason["en"])


def _enqueue_reserved_task(task_id: str, language: str = "en") -> str | None:
    """Return a safe diagnostic on enqueue failure; keep the persisted task queued."""
    try:
        job_id = _run_async(enqueue_coding_task, task_id)
    except Exception as exc:
        logger.exception(
            "Failed to enqueue coding task; task remains queued for worker reconciliation task_id=%s",
            task_id,
        )
        return _safe_enqueue_reason(exc, language)

    logger.info("Coding task enqueued task_id=%s job_id=%s", task_id, job_id)
    return None


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
                bot.reply_to(message, t(language, "github_connected", login=installation.github_login or "GitHub"), reply_markup=_main_keyboard(language))
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

    @bot.message_handler(commands=["balance"])
    def balance_command(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        try:
            credits, plan = ensure_user_credit_state(user_id)
            bot.reply_to(message, t(language, "balance", credits=credits, plan=plan), reply_markup=_main_keyboard(language))
        except BillingError:
            bot.reply_to(message, t(language, "billing_error"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["language"])
    def language_command(message: Message) -> None:
        if not message.from_user:
            return
        language = _language(message.from_user.id)
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
                bot.send_message(call.message.chat.id, t(language, "menu_home"), reply_markup=_main_keyboard(language), parse_mode="HTML")
        except Exception:
            logger.exception("Language selection failed")
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
        language = _language(user_id)
        bot.reply_to(message, t(language, "connect_button_hint"), reply_markup=_connect_markup(user_id, language))

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
        installation = _installation(user_id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language))
            return
        try:
            data = _run_async(github_app_get, "/installation/repositories?per_page=100", installation.installation_id)
            repos = data.get("repositories", [])
            if not repos:
                bot.reply_to(message, t(language, "repos_empty"), reply_markup=_main_keyboard(language))
                return
            lines = [f"• {repo.get('full_name')}" for repo in repos[:50] if repo.get("full_name")]
            bot.reply_to(message, t(language, "repos_title") + "\n\n" + "\n".join(lines), reply_markup=_main_keyboard(language))
        except Exception:
            logger.exception("Failed to list repositories")
            bot.reply_to(message, t(language, "github_error"), reply_markup=_main_keyboard(language))

    @bot.message_handler(commands=["task"])
    def task(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        installation = _installation(user_id)
        if not installation:
            bot.reply_to(message, t(language, "connect_first"), reply_markup=_connect_markup(user_id, language))
            return

        raw_task = (message.text or "")[len("/task"):].strip()
        if len(raw_task) < 3 or raw_task.startswith("/"):
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language))
            return

        explicit_match = TASK_REPO_REQUEST_RE.match(raw_task)
        explicit_repository = explicit_match.group("repository") if explicit_match else None
        request = explicit_match.group("request").strip() if explicit_match else raw_task

        if len(request) < 3:
            bot.reply_to(message, t(language, "task_format"), reply_markup=_main_keyboard(language))
            return

        try:
            data = _run_async(github_app_get, "/installation/repositories?per_page=100", installation.installation_id)
            repositories = [repo.get("full_name") for repo in data.get("repositories", []) if repo.get("full_name")]
        except Exception:
            logger.exception("Failed to resolve repositories for task")
            bot.reply_to(message, t(language, "github_error"), reply_markup=_main_keyboard(language))
            return

        if explicit_repository:
            if explicit_repository not in repositories:
                bot.reply_to(message, t(language, "invalid_repo"), reply_markup=_main_keyboard(language))
                return
            repository = explicit_repository
        elif len(repositories) == 1:
            repository = repositories[0]
        else:
            bot.reply_to(message, t(language, "task_choose_repo", count=len(repositories)), reply_markup=_main_keyboard(language))
            return

        estimated_credits = estimate_task_credits(request)
        try:
            reservation = reserve_task_credits(
                user_id,
                repository,
                request,
                estimated_credits,
                installation_id=installation.installation_id,
                model=settings.gemini_model,
                chat_id=message.chat.id,
                language=language,
            )
        except BillingError as exc:
            if str(exc) == "Insufficient credits":
                try:
                    credits, plan = ensure_user_credit_state(user_id)
                except BillingError:
                    credits, plan = 0, "free"
                bot.reply_to(message, t(language, "insufficient_credits", credits=credits, required=estimated_credits, plan=plan), reply_markup=_main_keyboard(language))
            elif str(exc) == "Active task already exists":
                bot.reply_to(message, t(language, "task_already_running"), reply_markup=_main_keyboard(language))
            else:
                bot.reply_to(message, t(language, "billing_error"), reply_markup=_main_keyboard(language))
            return

        enqueue_error = _enqueue_reserved_task(reservation.task_id, language)
        if enqueue_error:
            if language == "fa":
                queue_message = (
                    "ارسال وظیفه به صف ناموفق شد. علت تشخیص‌داده‌شده: "
                    f"{enqueue_error}\n"
                    "وظیفه در پایگاه داده با وضعیت queued باقی مانده و اعتبار آن دوباره کسر نشده است؛ "
                    "لطفاً درخواست را تکرار نکن."
                )
            elif language == "hi":
                queue_message = (
                    "कार्य को queue में भेजना विफल हुआ। पहचाना गया कारण: "
                    f"{enqueue_error}\n"
                    "कार्य database में queued है और क्रेडिट दोबारा नहीं काटे गए हैं; कृपया अनुरोध दोबारा न भेजें।"
                )
            else:
                queue_message = (
                    "Submitting the task to the queue failed. Detected reason: "
                    f"{enqueue_error}\n"
                    "The task remains queued in the database and its credits were not charged again; please do not resubmit."
                )
            bot.reply_to(message, queue_message[:4000], reply_markup=_main_keyboard(language))
            return

        bot.reply_to(
            message,
            t(language, "task_received_with_cost", credits=estimated_credits, remaining=reservation.remaining),
            reply_markup=_main_keyboard(language),
        )


    @bot.pre_checkout_query_handler(func=lambda query: True)
    def stars_pre_checkout(query) -> None:
        try:
            with SessionLocal() as db:
                valid = validate_stars_precheckout(
                    db, query.invoice_payload, query.from_user.id, query.currency, query.total_amount
                )
            if valid:
                bot.answer_pre_checkout_query(query.id, ok=True)
            else:
                bot.answer_pre_checkout_query(query.id, ok=False, error_message="This invoice is invalid or expired. Please create a new invoice.")
        except Exception:
            logger.exception("Telegram Stars pre-checkout validation failed")
            try:
                bot.answer_pre_checkout_query(query.id, ok=False, error_message="Payment validation failed. Please try again.")
            except Exception:
                logger.exception("Could not reject Telegram Stars pre-checkout")

    @bot.message_handler(content_types=["successful_payment"])
    def stars_successful_payment(message: Message) -> None:
        if not message.from_user or not message.successful_payment:
            return
        paid = message.successful_payment
        payload = paid.invoice_payload or ""
        try:
            parts = payload.split(":")
            if len(parts) != 4 or parts[0] != "xai" or int(parts[3]) != message.from_user.id:
                logger.warning("Ignoring malformed Telegram Stars payload for user_id=%s", message.from_user.id)
                return
            payment_id = parts[1]
            with SessionLocal() as db:
                confirm_stars_payment(
                    db,
                    payment_id=payment_id,
                    telegram_id=message.from_user.id,
                    currency=paid.currency,
                    total_amount=paid.total_amount,
                    charge_id=paid.telegram_payment_charge_id,
                    provider_charge_id=paid.provider_payment_charge_id,
                )
            language = _language(message.from_user.id)
            bot.send_message(
                message.chat.id,
                "پرداخت Stars تأیید شد و اشتراک فعال شد." if language == "fa"
                else "Stars payment confirmed and subscription activated.",
            )
        except StarsPaymentError as exc:
            logger.warning("Telegram Stars payment was not activated: %s", exc)
            bot.send_message(
                message.chat.id,
                "پرداخت دریافت شد اما فعال‌سازی نیاز به بررسی پشتیبانی دارد." if _language(message.from_user.id) == "fa"
                else "Payment received, but activation needs support review.",
            )
        except Exception:
            logger.exception("Telegram Stars successful-payment handler failed")
            bot.send_message(
                message.chat.id,
                "پرداخت دریافت شد اما فعال‌سازی نیاز به بررسی پشتیبانی دارد." if _language(message.from_user.id) == "fa"
                else "Payment received, but activation needs support review.",
            )

    @bot.message_handler(commands=["paysupport"])
    def payment_support(message: Message) -> None:
        language = _language(message.from_user.id) if message.from_user else "en"
        text = {
            "fa": "برای مشکلات پرداخت Stars، لطفاً شناسه تلگرام، پلن خریداری‌شده و زمان پرداخت را ارسال کن. اطلاعات محرمانه یا کد ورود را نفرست.",
            "hi": "For Stars payment support, send your Telegram ID, purchased plan, and payment time. Do not send passwords or login codes.",
            "en": "For Stars payment support, send your Telegram ID, purchased plan, and payment time. Do not send passwords or login codes.",
        }
        bot.reply_to(message, text.get(language, text["en"]))

    @bot.message_handler(commands=["terms"])
    def payment_terms(message: Message) -> None:
        language = _language(message.from_user.id) if message.from_user else "en"
        text = {
            "fa": "شرایط اشتراک XAI: اشتراک Pro و Team برای ۳۰ روز فعال می‌شود. خدمات دیجیتال پس از تأیید successful_payment در تلگرام فعال می‌شوند. برای مشکلات پرداخت از /paysupport استفاده کن.",
            "hi": "XAI subscription terms: Pro and Team subscriptions are active for 30 days. Digital services are activated only after Telegram confirms successful_payment. Use /paysupport for payment issues.",
            "en": "XAI subscription terms: Pro and Team subscriptions are active for 30 days. Digital services are activated only after Telegram confirms successful_payment. Use /paysupport for payment issues.",
        }
        bot.reply_to(message, text.get(language, text["en"]))


    @bot.message_handler(func=lambda message: bool(message.text))
    def menu_buttons(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        language = _language(user_id)
        text = (message.text or "").strip()
        if text == t(language, "connect_menu_button"):
            connect_command(message)
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
