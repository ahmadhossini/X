from __future__ import annotations

from telebot import types

from bot.services.language_service import get_text
from bot.services.user_language import get_user_language, set_user_language

SUPPORT_URL = "https://t.me/XAIMASTER_Official"


def language_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("• فارسی", callback_data="v3lang:fa"),
        types.InlineKeyboardButton("• English", callback_data="v3lang:en"),
    )
    return markup


def start_keyboard(language: str, bot_username: str, miniapp_url: str = "") -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_text(language, "add_group"), url=f"https://t.me/{bot_username}?startgroup=true"))
    if miniapp_url:
        markup.add(types.InlineKeyboardButton(get_text(language, "dashboard"), web_app=types.WebAppInfo(url=miniapp_url)))
    markup.add(types.InlineKeyboardButton(get_text(language, "support"), url=SUPPORT_URL))
    return markup


def render_start(bot, message, language: str, miniapp_url: str = "") -> None:
    text = (
        get_text(language, "welcome", name=message.from_user.first_name or "User")
        + "\n\n"
        + get_text(language, "features")
        + "\n\n"
        + get_text(language, "admin_info")
    )
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=start_keyboard(language, bot.get_me().username, miniapp_url),
    )


def language_for_user(user_id: int) -> str | None:
    return get_user_language(user_id)


def save_language(user_id: int, language: str) -> None:
    set_user_language(user_id, language)
