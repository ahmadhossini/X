from __future__ import annotations

import logging
from typing import Optional

from telebot import TeleBot, types
from telebot.types import Message

from bot.services.moderation import GroupModeration
from bot.services.user_language import get_user_language, set_user_language
from bot.services.language_service import get_text
from core.config import settings

logger = logging.getLogger(__name__)

SUPPORT_URL = "https://t.me/XAIMASTER_Official"
DEFAULT_MINIAPP_URL = "https://xai-master-production-c83b.up.railway.app/miniapp/"


def lang_for(message: Message) -> str:
    try:
        return get_user_language(message.from_user.id) or "fa"
    except Exception:
        return "fa"


def choose_language_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("• فارسی", callback_data="lang:fa"),
        types.InlineKeyboardButton("• English", callback_data="lang:en"),
    )
    return markup


def get_bot_username(bot: TeleBot) -> str:
    try:
        username = bot.get_me().username
        if username:
            return username.lstrip("@")
    except Exception:
        logger.exception("could not get bot username")
    return ""


def start_keyboard(bot: TeleBot, lang: str):
    markup = types.InlineKeyboardMarkup()
    bot_username = get_bot_username(bot)
    miniapp_url = getattr(settings, "miniapp_url", "") or DEFAULT_MINIAPP_URL
    if bot_username:
        markup.add(types.InlineKeyboardButton(get_text(lang, "add_group"), url=f"https://t.me/{bot_username}?startgroup=true"))
    if miniapp_url:
        markup.add(types.InlineKeyboardButton(get_text(lang, "dashboard"), web_app=types.WebAppInfo(url=miniapp_url)))
    markup.add(types.InlineKeyboardButton(get_text(lang, "support"), url=SUPPORT_URL))
    return markup


def send_start(bot: TeleBot, message: Message, lang: str):
    name = message.from_user.first_name or "User"
    try:
        text = get_text(lang, "welcome", name=name) + "\n\n" + get_text(lang, "features") + "\n\n" + get_text(lang, "admin")
    except Exception:
        text = "<b>XAI MASTER V3</b>\n\nAI Telegram Group Manager"
    bot.send_message(message.chat.id, text, reply_markup=start_keyboard(bot, lang), parse_mode="HTML")


def _target_from_reply(message: Message) -> Optional[int]:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    return None


def build_bot():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is missing")

    bot = TeleBot(settings.bot_token, parse_mode="HTML")
    moderation = GroupModeration(bot)

    def is_admin(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            return False
        try:
            member = bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {"creator", "administrator"}
        except Exception:
            return False

    @bot.message_handler(commands=["start"])
    def start_command(message: Message):
        lang = lang_for(message)
        parts = (message.text or "").split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""

        if message.chat.type == "private" and payload.startswith("panel_"):
            chat_id = payload.removeprefix("panel_")
            if chat_id.startswith("-"):
                miniapp_url = getattr(settings, "miniapp_url", "") or DEFAULT_MINIAPP_URL
                separator = "&" if "?" in miniapp_url else "?"
                url = f"{miniapp_url}{separator}chat_id={chat_id}"
                bot.send_message(
                    message.chat.id,
                    "<b>XAI MASTER V3 PANEL</b>\n\nپنل مدیریت گروه شما آماده است.",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("• باز کردن پنل مدیریت", web_app=types.WebAppInfo(url=url))
                    ),
                    parse_mode="HTML",
                )
                return

        if not get_user_language(message.from_user.id):
            bot.send_message(message.chat.id, "• لطفاً زبان را انتخاب کنید\n• Please select your language:", reply_markup=choose_language_keyboard())
            return
        send_start(bot, message, lang)

    @bot.message_handler(commands=["help", "راهنما"])
    def help_command(message: Message):
        lang = lang_for(message)
        try:
            send_start(bot, message, lang)
        except Exception:
            bot.reply_to(message, "<b>XAI MASTER V3</b>\nCommands:\n/panel\n/warn\n/settings")

    @bot.message_handler(commands=["panel", "پنل"])
    def panel_command(message: Message):
        try:
            miniapp_url = getattr(settings, "miniapp_url", "") or DEFAULT_MINIAPP_URL
            if message.chat.type in {"group", "supergroup"}:
                bot_username = get_bot_username(bot)
                if not bot_username:
                    bot.send_message(message.chat.id, "نام کاربری ربات از Telegram دریافت نشد. ربات را دوباره راه‌اندازی کنید.")
                    return
                deep_link = f"https://t.me/{bot_username}?start=panel_{message.chat.id}"
                bot.send_message(
                    message.chat.id,
                    "<b>XAI MASTER V3 PANEL</b>\n\nبرای مدیریت این گروه، ابتدا پنل را در چت خصوصی ربات باز کنید:",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("• باز کردن پنل مدیریت", url=deep_link)
                    ),
                    parse_mode="HTML",
                )
                return

            bot.send_message(
                message.chat.id,
                "<b>XAI MASTER V3 PANEL</b>",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("• باز کردن پنل مدیریت", web_app=types.WebAppInfo(url=miniapp_url))
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("panel error")
            try:
                bot.send_message(message.chat.id, "پنل مدیریت موقتاً در دسترس نیست.")
            except Exception:
                logger.exception("panel fallback error")

    @bot.message_handler(commands=["warn", "هشدار"])
    def warn_command(message: Message):
        lang = lang_for(message)
        if not is_admin(message):
            bot.reply_to(message, get_text(lang, "only_admin"))
            return
        user_id = _target_from_reply(message)
        if not user_id:
            bot.reply_to(message, "Reply to a user message first.")
            return
        try:
            count = moderation.warn(message.chat.id, user_id, "Manual warning")
            bot.reply_to(message, f"Warning added. Total warnings: {count}")
        except Exception:
            logger.exception("warn error")
            bot.reply_to(message, "Warning failed.")

    @bot.message_handler(commands=["settings", "تنظیمات"])
    def settings_command(message: Message):
        lang = lang_for(message)
        if not is_admin(message):
            bot.reply_to(message, get_text(lang, "only_admin"))
            return
        bot.reply_to(message, "<b>XAI MASTER SETTINGS</b>\n\nبرای تنظیمات کامل گروه از /panel استفاده کنید.")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("lang:"))
    def language_callback(call):
        lang = call.data.split(":", 1)[1]
        if lang not in {"fa", "en"}:
            bot.answer_callback_query(call.id, "Invalid language")
            return
        set_user_language(call.from_user.id, lang)
        bot.answer_callback_query(call.id)
        send_start(bot, call.message, lang)

    @bot.message_handler(commands=["ban"])
    def ban_command(message: Message):
        lang = lang_for(message)
        if not is_admin(message):
            bot.reply_to(message, get_text(lang, "only_admin"))
            return
        user_id = _target_from_reply(message)
        if not user_id:
            bot.reply_to(message, "Reply to user message.")
            return
        try:
            bot.ban_chat_member(message.chat.id, user_id)
            bot.reply_to(message, "User banned.")
        except Exception:
            logger.exception("ban error")
            bot.reply_to(message, "Ban failed.")

    @bot.message_handler(commands=["unban"])
    def unban_command(message: Message):
        lang = lang_for(message)
        if not is_admin(message):
            bot.reply_to(message, get_text(lang, "only_admin"))
            return
        user_id = _target_from_reply(message)
        if not user_id:
            bot.reply_to(message, "Reply to user message.")
            return
        try:
            bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
            bot.reply_to(message, "User unbanned.")
        except Exception:
            logger.exception("unban error")
            bot.reply_to(message, "Unban failed.")

    @bot.message_handler(commands=["unmute", "رفع_محدودیت"])
    def unmute_command(message: Message):
        if not is_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            bot.reply_to(message, "Reply to user message.")
            return
        try:
            bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=True, can_send_media_messages=True)
            bot.reply_to(message, "User unmuted.")
        except Exception:
            logger.exception("unmute error")

    @bot.message_handler(content_types=["new_chat_members"])
    def verify_new_members(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            return
        for member in message.new_chat_members:
            if member.is_bot:
                continue
            try:
                bot.restrict_chat_member(message.chat.id, member.id, can_send_messages=False)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("• Verify", callback_data=f"verify:{message.chat.id}:{member.id}"))
                bot.send_message(message.chat.id, "Please verify you are human.", reply_markup=markup)
            except Exception:
                logger.exception("verify error")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("verify:"))
    def verify_callback(call):
        try:
            _, chat_id, user_id = call.data.split(":")
            chat_id = int(chat_id)
            user_id = int(user_id)
            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "Not for you", show_alert=True)
                return
            bot.restrict_chat_member(chat_id, user_id, can_send_messages=True, can_send_media_messages=True)
            bot.answer_callback_query(call.id, "Verified")
            bot.edit_message_text("Verified", chat_id, call.message.message_id)
        except Exception:
            logger.exception("verification error")
            bot.answer_callback_query(call.id, "Verification failed", show_alert=True)

    @bot.message_handler(content_types=["text", "photo", "video", "document", "animation", "audio", "voice", "sticker"])
    def moderation_handler(message: Message):
        if message.chat.type in {"group", "supergroup"}:
            try:
                moderation.handle(message)
            except Exception:
                logger.exception("moderation error")

    return bot


def run_bot():
    bot = build_bot()
    logger.info("XAI MASTER V3 started")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
