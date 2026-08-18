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


def lang_for(message: Message) -> str:
    try:
        return get_user_language(message.from_user.id) or "fa"
    except Exception:
        return "fa"


def choose_language_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "• فارسی",
            callback_data="lang:fa"
        ),
        types.InlineKeyboardButton(
            "• English",
            callback_data="lang:en"
        )
    )
    return markup


def start_keyboard(lang: str):
    markup = types.InlineKeyboardMarkup()

    bot_username = getattr(
        settings,
        "bot_username",
        "XAI_MASTER_BOT"
    )

    miniapp_url = getattr(
        settings,
        "miniapp_url",
        ""
    )

    markup.add(
        types.InlineKeyboardButton(
            get_text(lang, "add_group"),
            url=f"https://t.me/{bot_username}?startgroup=true"
        )
    )

    if miniapp_url:
        markup.add(
            types.InlineKeyboardButton(
                get_text(lang, "dashboard"),
                web_app=types.WebAppInfo(
                    url=miniapp_url
                )
            )
        )

    markup.add(
        types.InlineKeyboardButton(
            get_text(lang, "support"),
            url=SUPPORT_URL
        )
    )

    return markup


def send_start(
    bot: TeleBot,
    message: Message,
    lang: str
):
    name = (
        message.from_user.first_name
        or "User"
    )

    try:
        text = (
            get_text(
                lang,
                "welcome",
                name=name
            )
            + "\n\n"
            + get_text(lang, "features")
            + "\n\n"
            + get_text(lang, "admin")
        )
    except Exception:
        text = (
            "<b>XAI MASTER V3</b>\n\n"
            "AI Telegram Group Manager"
        )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=start_keyboard(lang),
        parse_mode="HTML"
    )


def _target_from_reply(
    message: Message
) -> Optional[int]:
    if (
        message.reply_to_message
        and message.reply_to_message.from_user
    ):
        return message.reply_to_message.from_user.id
    return None


def build_bot():
    if not settings.bot_token:
        raise RuntimeError(
            "BOT_TOKEN is missing"
        )

    bot = TeleBot(
        settings.bot_token,
        parse_mode="HTML"
    )

    moderation = GroupModeration(bot)

    def is_admin(message: Message):
        if message.chat.type not in {
            "group",
            "supergroup"
        }:
            return False

        try:
            member = bot.get_chat_member(
                message.chat.id,
                message.from_user.id
            )

            return member.status in {
                "creator",
                "administrator"
            }

        except Exception:
            return False

    @bot.message_handler(
        commands=[
            "start"
        ]
    )
    def start_command(message: Message):
        lang = lang_for(message)

        if not get_user_language(
            message.from_user.id
        ):
            bot.send_message(
                message.chat.id,
                "• لطفاً زبان را انتخاب کنید\n• Please select your language:",
                reply_markup=choose_language_keyboard()
            )
            return

        send_start(
            bot,
            message,
            lang
        )

    @bot.message_handler(
        commands=[
            "help",
            "راهنما"
        ]
    )
    def help_command(message: Message):
        lang = lang_for(message)

        try:
            send_start(
                bot,
                message,
                lang
            )

        except Exception:
            bot.reply_to(
                message,
                "<b>XAI MASTER V3</b>\n"
                "Commands:\n"
                "/panel\n"
                "/warn\n"
                "/settings"
            )

    @bot.message_handler(
        commands=[
            "panel",
            "پنل"
        ]
    )
    def panel_command(message: Message):
        lang = lang_for(message)

        miniapp_url = getattr(
            settings,
            "miniapp_url",
            ""
        )

        if not miniapp_url:
            bot.reply_to(
                message,
                "Dashboard is not configured."
            )
            return

        markup = types.InlineKeyboardMarkup()

        markup.add(
            types.InlineKeyboardButton(
                "• Dashboard",
                web_app=types.WebAppInfo(
                    url=miniapp_url
                )
            )
        )

        bot.reply_to(
            message,
            "<b>XAI MASTER V3 PANEL</b>",
            reply_markup=markup
        )

    @bot.message_handler(
        commands=[
            "warn",
            "هشدار"
        ]
    )
    def warn_command(message: Message):
        lang = lang_for(message)

        if not is_admin(message):
            bot.reply_to(
                message,
                get_text(
                    lang,
                    "only_admin"
                )
            )
            return

        user_id = _target_from_reply(message)

        if not user_id:
            bot.reply_to(
                message,
                "Reply to a user message first."
            )
            return

        try:
            count = moderation.warn(
                message.chat.id,
                user_id,
                "Manual warning"
            )

            bot.reply_to(
                message,
                f"Warning added. Total warnings: {count}"
            )

        except Exception:
            logger.exception("warn error")
            bot.reply_to(
                message,
                "Warning failed."
            )

    @bot.message_handler(
        commands=[
            "settings",
            "تنظیمات"
        ]
    )
    def settings_command(message: Message):
        lang = lang_for(message)

        if not is_admin(message):
            bot.reply_to(
                message,
                get_text(
                    lang,
                    "only_admin"
                )
            )
            return

        text = (
            "<b>XAI MASTER SETTINGS</b>\n\n"
            "• Anti Link\n"
            "• Anti Flood\n"
            "• Anti Spam\n"
            "• Forward Lock\n"
            "• Mention Lock\n"
            "• Hashtag Lock\n"
            "• Phone Lock\n"
            "• Profanity Filter\n"
            "• Drug Filter\n"
            "• NSFW Filter"
        )

        bot.reply_to(
            message,
            text
        )

    @bot.callback_query_handler(
        func=lambda call:
        call.data
        and call.data.startswith(
            "lang:"
        )
    )
    def language_callback(call):
        lang = call.data.split(
            ":",
            1
        )[1]

        if lang not in {
            "fa",
            "en"
        }:
            bot.answer_callback_query(
                call.id,
                "Invalid language"
            )
            return

        set_user_language(
            call.from_user.id,
            lang
        )

        bot.answer_callback_query(call.id)

        send_start(
            bot,
            call.message,
            lang
        )

    @bot.message_handler(
        commands=[
            "ban"
        ]
    )
    def ban_command(message: Message):
        lang = lang_for(message)

        if not is_admin(message):
            bot.reply_to(
                message,
                get_text(
                    lang,
                    "only_admin"
                )
            )
            return

        user_id = _target_from_reply(message)

        if not user_id:
            bot.reply_to(
                message,
                "Reply to user message."
            )
            return

        try:
            bot.ban_chat_member(
                message.chat.id,
                user_id
            )

            bot.reply_to(
                message,
                "User banned."
            )

        except Exception:
            logger.exception("ban error")
            bot.reply_to(
                message,
                "Ban failed."
            )

    @bot.message_handler(
        commands=[
            "unban"
        ]
    )
    def unban_command(message: Message):
        lang = lang_for(message)

        if not is_admin(message):
            bot.reply_to(
                message,
                get_text(
                    lang,
                    "only_admin"
                )
            )
            return

        user_id = _target_from_reply(message)

        if not user_id:
            bot.reply_to(
                message,
                "Reply to user message."
            )
            return

        try:
            bot.unban_chat_member(
                message.chat.id,
                user_id,
                only_if_banned=True
            )

            bot.reply_to(
                message,
                "User unbanned."
            )

        except Exception:
            logger.exception("unban error")
            bot.reply_to(
                message,
                "Unban failed."
            )

    @bot.message_handler(
        commands=[
            "unmute",
            "رفع_محدودیت"
        ]
    )
    def unmute_command(message: Message):
        if not is_admin(message):
            return

        user_id = _target_from_reply(message)

        if not user_id:
            bot.reply_to(
                message,
                "Reply to user message."
            )
            return

        try:
            bot.restrict_chat_member(
                message.chat.id,
                user_id,
                can_send_messages=True,
                can_send_media_messages=True
            )

            bot.reply_to(
                message,
                "User unmuted."
            )

        except Exception:
            logger.exception("unmute error")

    @bot.message_handler(
        content_types=[
            "new_chat_members"
        ]
    )
    def verify_new_members(message: Message):
        if message.chat.type not in {
            "group",
            "supergroup"
        }:
            return

        for member in message.new_chat_members:
            if member.is_bot:
                continue

            try:
                bot.restrict_chat_member(
                    message.chat.id,
                    member.id,
                    can_send_messages=False
                )

                markup = types.InlineKeyboardMarkup()

                markup.add(
                    types.InlineKeyboardButton(
                        "• Verify",
                        callback_data=(
                            f"verify:"
                            f"{message.chat.id}:"
                            f"{member.id}"
                        )
                    )
                )

                bot.send_message(
                    message.chat.id,
                    "Please verify you are human.",
                    reply_markup=markup
                )

            except Exception:
                logger.exception("verify error")

    @bot.callback_query_handler(
        func=lambda call:
        call.data
        and call.data.startswith(
            "verify:"
        )
    )
    def verify_callback(call):
        try:
            _, chat_id, user_id = call.data.split(":")

            chat_id = int(chat_id)
            user_id = int(user_id)

            if call.from_user.id != user_id:
                bot.answer_callback_query(
                    call.id,
                    "Not for you",
                    show_alert=True
                )
                return

            bot.restrict_chat_member(
                chat_id,
                user_id,
                can_send_messages=True,
                can_send_media_messages=True
            )

            bot.answer_callback_query(
                call.id,
                "Verified"
            )

            bot.edit_message_text(
                "Verified",
                chat_id,
                call.message.message_id
            )

        except Exception:
            logger.exception("verification error")
            bot.answer_callback_query(
                call.id,
                "Verification failed",
                show_alert=True
            )

    @bot.message_handler(
        content_types=[
            "text",
            "photo",
            "video",
            "document",
            "animation",
            "audio",
            "voice",
            "sticker"
        ]
    )
    def moderation_handler(message: Message):
        if message.chat.type in {
            "group",
            "supergroup"
        }:
            try:
                moderation.handle(message)
            except Exception:
                logger.exception("moderation error")

    return bot


def run_bot():
    bot = build_bot()

    logger.info(
        "XAI MASTER V3 started"
    )

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO
    )

    run_bot()
