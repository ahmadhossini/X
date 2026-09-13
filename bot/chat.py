from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google import genai
from sqlalchemy import func, select
from telebot import types
from telebot.types import Message

from bot.locales import t
from core.config import settings
from database.models import FreeChatUsage, User
from database.session import SessionLocal

FREE_CHAT_DAILY_LIMIT = 10
MAX_CHAT_MESSAGE_LENGTH = 4000


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


def _reserve_free_message(telegram_id: int) -> tuple[bool, int, int | None]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
        if user is None:
            user = User(telegram_id=telegram_id, language="en")
            db.add(user)
            db.flush()

        used = db.scalar(
            select(func.count(FreeChatUsage.id)).where(
                FreeChatUsage.user_id == user.id,
                FreeChatUsage.created_at >= since,
            )
        ) or 0
        if used >= FREE_CHAT_DAILY_LIMIT:
            db.rollback()
            return False, 0, None

        usage = FreeChatUsage(user_id=user.id, created_at=now)
        db.add(usage)
        db.flush()
        usage_id = usage.id
        db.commit()
        return True, FREE_CHAT_DAILY_LIMIT - used - 1, usage_id


def _release_free_message(telegram_id: int, usage_id: int | None) -> None:
    if usage_id is None:
        return
    with SessionLocal() as db:
        usage = db.scalar(
            select(FreeChatUsage)
            .join(User, User.id == FreeChatUsage.user_id)
            .where(FreeChatUsage.id == usage_id, User.telegram_id == telegram_id)
            .with_for_update()
        )
        if usage:
            db.delete(usage)
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

    allowed, _remaining, usage_id = _reserve_free_message(message.from_user.id)
    if not allowed:
        bot.reply_to(message, t(language, "free_chat_limit"), reply_markup=_purchase_markup(language))
        return

    try:
        reply = _generate_reply(text_value, language)
        bot.reply_to(message, reply)
    except Exception:
        _release_free_message(message.from_user.id, usage_id)
        bot.reply_to(message, t(language, "chat_error"))
