from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google import genai
from sqlalchemy import func, select
from telebot.types import Message

from bot.locales import t
from core.config import settings
from database.models import FreeChatUsage, User
from database.session import SessionLocal

FREE_CHAT_DAILY_LIMIT = 10
MAX_CHAT_MESSAGE_LENGTH = 4000


async def _generate_reply(text: str, language: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    language_name = {"fa": "Persian (Farsi)", "hi": "Hindi", "en": "English"}.get(language, "English")
    prompt = (
        "You are XAI Code Agent's general assistant. Answer the user's message naturally and helpfully. "
        "If the user asks about coding, explain clearly and provide useful code when appropriate. "
        f"Reply in {language_name} unless the user clearly asks for another language. "
        "Do not claim to have changed a GitHub repository unless a coding task was actually executed.\n\n"
        f"User message:\n{text}"
    )
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model or "gemini-2.5-flash",
        contents=prompt,
    )
    reply = (response.text or "").strip()
    if not reply:
        raise RuntimeError("Empty AI response")
    return reply[:4096]


def _reserve_free_message(telegram_id: int) -> tuple[bool, int]:
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
            return False, 0

        db.add(FreeChatUsage(user_id=user.id, created_at=now))
        db.commit()
        return True, FREE_CHAT_DAILY_LIMIT - used - 1


def handle_chat_message(bot, message: Message) -> None:
    if not message.from_user or not message.text:
        return

    text = message.text.strip()
    if not text or len(text) > MAX_CHAT_MESSAGE_LENGTH:
        return

    language = "en"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if user and user.language in {"fa", "en", "hi"}:
            language = user.language

    allowed, remaining = _reserve_free_message(message.from_user.id)
    if not allowed:
        bot.reply_to(message, t(language, "free_chat_limit"))
        return

    try:
        reply = _run_async(_generate_reply, text, language)
        bot.reply_to(message, reply)
    except Exception:
        # Do not consume a free message when the provider fails.
        with SessionLocal() as db:
            usage = db.scalar(
                select(FreeChatUsage)
                .join(User, FreeChatUsage.user_id == User.id)
                .where(User.telegram_id == message.from_user.id)
                .order_by(FreeChatUsage.created_at.desc())
            )
            if usage:
                db.delete(usage)
                db.commit()
        bot.reply_to(message, t(language, "chat_error"))


def _run_async(func, *args):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
