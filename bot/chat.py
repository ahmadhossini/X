from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google import genai
from sqlalchemy import select, text
from telebot import types
from telebot.types import Message

from bot.locales import t
from core.config import settings
from database.models import User
from database.session import SessionLocal

FREE_CHAT_DAILY_LIMIT = 10
MAX_CHAT_MESSAGE_LENGTH = 4000


def _ensure_usage_table() -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS free_chat_usage ("
                "user_id INTEGER NOT NULL, created_at TIMESTAMP NOT NULL)"
            )
        )
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_free_chat_usage_user_created ON free_chat_usage (user_id, created_at)"))
        db.commit()


def _generate_reply(text_value: str, language: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    language_name = {"fa": "Persian (Farsi)", "hi": "Hindi", "en": "English"}.get(language, "English")
    prompt = (
        "You are XAI Code Agent's general assistant. Answer the user's message naturally and helpfully. "
        "If the user asks about coding, explain clearly and provide useful code when appropriate. "
        f"Reply in {language_name} unless the user clearly asks for another language. "
        "Do not claim to have changed a GitHub repository unless a coding task was actually executed.\n\n"
        f"User message:\n{text_value}"
    )
    with genai.Client(api_key=settings.gemini_api_key) as client:
        response = client.models.generate_content(
            model=settings.gemini_model or "gemini-2.5-flash",
            contents=prompt,
        )
    reply = (response.text or "").strip()
    if not reply:
        raise RuntimeError("Empty AI response")
    return reply[:4096]


def _reserve_free_message(telegram_id: int) -> tuple[bool, int]:
    _ensure_usage_table()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if user is None:
            user = User(telegram_id=telegram_id, language="en")
            db.add(user)
            db.flush()

        used = db.scalar(
            text("SELECT COUNT(*) FROM free_chat_usage WHERE user_id = :user_id AND created_at >= :since"),
            {"user_id": user.id, "since": since},
        ) or 0
        if used >= FREE_CHAT_DAILY_LIMIT:
            db.rollback()
            return False, 0

        db.execute(
            text("INSERT INTO free_chat_usage (user_id, created_at) VALUES (:user_id, :created_at)"),
            {"user_id": user.id, "created_at": now},
        )
        db.commit()
        return True, FREE_CHAT_DAILY_LIMIT - used - 1


def _release_last_free_message(telegram_id: int) -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM free_chat_usage WHERE user_id = "
                "(SELECT id FROM users WHERE telegram_id = :telegram_id) "
                "AND created_at = (SELECT MAX(created_at) FROM free_chat_usage WHERE user_id = "
                "(SELECT id FROM users WHERE telegram_id = :telegram_id))"
            ),
            {"telegram_id": telegram_id},
        )
        db.commit()


def _purchase_markup(language: str):
    url = settings.miniapp_url or f"{settings.public_base_url}/dashboard/"
    label = t(language, "buy_credits")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(label, web_app=types.WebAppInfo(url=url)))
    return markup


def handle_chat_message(bot, message: Message) -> None:
    if not message.from_user or not message.text:
        return

    text_value = message.text.strip()
    if not text_value or len(text_value) > MAX_CHAT_MESSAGE_LENGTH:
        return

    language = "en"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if user and user.language in {"fa", "en", "hi"}:
            language = user.language

    allowed, _remaining = _reserve_free_message(message.from_user.id)
    if not allowed:
        bot.reply_to(message, t(language, "free_chat_limit"), reply_markup=_purchase_markup(language))
        return

    try:
        reply = _generate_reply(text_value, language)
        bot.reply_to(message, reply)
    except Exception:
        _release_last_free_message(message.from_user.id)
        bot.reply_to(message, t(language, "chat_error"))
