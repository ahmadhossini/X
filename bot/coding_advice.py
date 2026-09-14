from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from google import genai
from sqlalchemy import select, text
from telebot.types import Message

from bot.locales import t
from core.config import settings
from database.models import User
from database.session import SessionLocal

FREE_ADVICE_DAILY_LIMIT = 10
MAX_ADVICE_MESSAGE_LENGTH = 4000


def _ensure_usage_table() -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS free_coding_advice_usage ("
                "user_id INTEGER NOT NULL, created_at TIMESTAMP NOT NULL)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_free_coding_advice_usage_user_created "
                "ON free_coding_advice_usage (user_id, created_at)"
            )
        )
        db.commit()


async def _generate_advice(text_value: str, language: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    language_name = {"fa": "Persian (Farsi)", "hi": "Hindi", "en": "English"}.get(language, "English")
    prompt = (
        "You are the coding advice assistant for XAI Code Agent. "
        "Give practical, accurate programming guidance. Explain the cause of problems clearly, "
        "suggest safe fixes, and provide code examples when useful. "
        "Do not claim to have inspected, changed, tested, committed, or pushed a GitHub repository. "
        "This assistant only provides advice; repository changes are handled by coding tasks. "
        f"Reply in {language_name} unless the user clearly asks for another language.\n\n"
        f"User question:\n{text_value}"
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


def _reserve_advice(telegram_id: int) -> bool:
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
            text(
                "SELECT COUNT(*) FROM free_coding_advice_usage "
                "WHERE user_id = :user_id AND created_at >= :since"
            ),
            {"user_id": user.id, "since": since},
        ) or 0
        if used >= FREE_ADVICE_DAILY_LIMIT:
            db.rollback()
            return False

        db.execute(
            text(
                "INSERT INTO free_coding_advice_usage (user_id, created_at) "
                "VALUES (:user_id, :created_at)"
            ),
            {"user_id": user.id, "created_at": now},
        )
        db.commit()
        return True


def _release_advice(telegram_id: int) -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM free_coding_advice_usage "
                "WHERE user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id) "
                "AND created_at = (SELECT MAX(created_at) FROM free_coding_advice_usage "
                "WHERE user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id))"
            ),
            {"telegram_id": telegram_id},
        )
        db.commit()


def handle_coding_advice(bot, message: Message) -> None:
    if not message.from_user or not message.text:
        return

    text_value = message.text.strip()
    if not text_value or len(text_value) > MAX_ADVICE_MESSAGE_LENGTH:
        return

    language = "en"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if user and user.language in {"fa", "en", "hi"}:
            language = user.language

    if not _reserve_advice(message.from_user.id):
        bot.reply_to(message, t(language, "free_chat_limit"))
        return

    try:
        reply = _run_async(_generate_advice, text_value, language)
        bot.reply_to(message, reply)
    except Exception:
        _release_advice(message.from_user.id)
        bot.reply_to(message, t(language, "chat_error"))


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
