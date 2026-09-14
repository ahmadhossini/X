from __future__ import annotations

import asyncio

from google import genai
from telebot.types import Message

from billing.service import BillingError, refund_advice_credit, reserve_advice_credit
from bot.locales import t
from core.config import settings
from database.models import User
from database.session import SessionLocal
from sqlalchemy import select

MAX_ADVICE_MESSAGE_LENGTH = 4000


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


def _language_for_user(telegram_id: int) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user and user.language in {"fa", "en", "hi"}:
            return user.language
    return "en"


def handle_coding_advice(bot, message: Message) -> None:
    if not message.from_user or not message.text:
        return

    text_value = message.text.strip()
    if not text_value or len(text_value) > MAX_ADVICE_MESSAGE_LENGTH:
        return

    telegram_id = message.from_user.id
    language = _language_for_user(telegram_id)

    try:
        reservation = reserve_advice_credit(telegram_id)
    except BillingError:
        bot.reply_to(message, t(language, "free_chat_limit"))
        return

    try:
        reply = _run_async(_generate_advice, text_value, language)
        bot.reply_to(message, reply)
    except Exception:
        refund_advice_credit(telegram_id)
        bot.reply_to(message, t(language, "chat_error"))


def _run_async(func, *args):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
