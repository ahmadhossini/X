from __future__ import annotations

import logging
import threading
from typing import Optional

from telebot import TeleBot, types
from telebot.types import Message

from bot.services.moderation import GroupModeration
from core.config import settings

logger = logging.getLogger(__name__)

TEXT = {
    "fa": {
        "start": "<b>XAI MASTER V3</b>\n\nمدیر هوشمند و محافظ گروه در حال اجراست.\n\n• مدیریت گروه\n• ضداسپم\n• ضدلینک\n• فیلتر محتوا\n• اخطار و محدودسازی\n• مدیر هوشمند\n• Mini App\n\nبرای مدیریت گروه، دستور یا درخواست خود را ارسال کنید.",
        "only_admin": "فقط مدیران گروه می‌توانند این دستور را اجرا کنند.",
        "reply": "روی پیام کاربر ریپلای کنید و دوباره دستور را بفرستید.",
        "unmuted": "محدودیت کاربر برداشته شد.",
        "unmute_fail": "نتوانستم محدودیت کاربر را بردارم. دسترسی لازم ربات را بررسی کنید.",
        "banned": "کاربر مسدود شد.",
        "ban_fail": "نتوانستم کاربر را مسدود کنم. دسترسی Ban را بررسی کنید.",
        "unbanned": "کاربر از مسدودی خارج شد.",
        "unban_fail": "نتوانستم مسدودی کاربر را بردارم.",
        "market": "مرکز بازار در Mini App قرار دارد. برای مشاهده قیمت‌ها، Mini App را باز کنید.",
        "panel_missing": "Mini App هنوز URL عمومی ندارد. پس از استقرار، گزینه پنل فعال می‌شود.",
        "verify": "• لطفاً برای تأیید انسان بودن خود روی دکمه زیر بزنید.\n• زمان تأیید: 60 ثانیه",
        "verify_btn": "• تأیید من",
        "verified": "• تأیید با موفقیت انجام شد.",
        "verify_wrong": "این تأیید برای کاربر دیگری است.",
        "verify_fail": "نتوانستم تأیید کاربر را ثبت کنم.",
    },
    "en": {
        "start": "<b>XAI MASTER V3</b>\n\nYour smart group manager and protection system is online.\n\n• Group Management\n• Anti-Spam\n• Anti-Link\n• Content Filtering\n• Warnings and Restrictions\n• AI Manager\n• Mini App\n\nSend a command or management request.",
        "only_admin": "Only group administrators can use this command.",
        "reply": "Reply to the user's message and send the command again.",
        "unmuted": "The user's restrictions were removed.",
        "unmute_fail": "I could not remove the restrictions. Check the bot's permissions.",
        "banned": "The user was banned.",
        "ban_fail": "I could not ban the user. Check the bot's Ban permission.",
        "unbanned": "The user was unbanned.",
        "unban_fail": "I could not remove the ban.",
        "market": "The Market Center is available in the Mini App. Open the Mini App to view prices.",
        "panel_missing": "The Mini App does not have a public URL yet. The panel will be enabled after deployment.",
        "verify": "• Please verify that you are human using the button below.\n• Verification time: 60 seconds",
        "verify_btn": "• Verify Me",
        "verified": "• Verification completed successfully.",
        "verify_wrong": "This verification belongs to another user.",
        "verify_fail": "I could not complete the verification.",
    },
}


def lang_for(message: Message) -> str:
    code = getattr(getattr(message, "from_user", None), "language_code", "") or ""
    return "en" if code.lower().startswith("en") else "fa"


def _target_from_reply(message: Message) -> Optional[int]:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    return None


def build_bot() -> TeleBot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = TeleBot(settings.bot_token, parse_mode="HTML")
    moderation = GroupModeration(bot)

    def is_admin(message: Message) -> bool:
        if message.chat.type not in {"group", "supergroup"}:
            return False
        try:
            member = bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in {"creator", "administrator"}
        except Exception:
            return False

    @bot.message_handler(commands=["start", "help"])
    def start(message: Message):
        bot.reply_to(message, TEXT[lang_for(message)]["start"])

    @bot.message_handler(commands=["panel"])
    def panel(message: Message):
        url = getattr(settings, "miniapp_url", "")
        if not url:
            bot.reply_to(message, TEXT[lang_for(message)]["panel_missing"])
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("• Open Mini App", web_app=types.WebAppInfo(url=url)))
        bot.reply_to(message, "<b>XAI MASTER V3</b>", reply_markup=markup)

    @bot.message_handler(commands=["market"])
    def market(message: Message):
        bot.reply_to(message, TEXT[lang_for(message)]["market"])

    @bot.message_handler(commands=["unmute", "رفع_محدودیت"])
    def unmute(message: Message):
        t = TEXT[lang_for(message)]
        if not is_admin(message):
            return bot.reply_to(message, t["only_admin"])
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, t["reply"])
        try:
            bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=True, can_send_audios=True,
                                     can_send_documents=True, can_send_photos=True, can_send_videos=True,
                                     can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
                                     can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, t["unmuted"])
        except Exception as exc:
            logger.exception("unmute failed: %s", exc)
            bot.reply_to(message, t["unmute_fail"])

    @bot.message_handler(commands=["ban"])
    def ban(message: Message):
        t = TEXT[lang_for(message)]
        if not is_admin(message):
            return bot.reply_to(message, t["only_admin"])
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, t["reply"])
        try:
            bot.ban_chat_member(message.chat.id, user_id)
            bot.reply_to(message, t["banned"])
        except Exception:
            bot.reply_to(message, t["ban_fail"])

    @bot.message_handler(commands=["unban"])
    def unban(message: Message):
        t = TEXT[lang_for(message)]
        if not is_admin(message):
            return bot.reply_to(message, t["only_admin"])
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, t["reply"])
        try:
            bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
            bot.reply_to(message, t["unbanned"])
        except Exception:
            bot.reply_to(message, t["unban_fail"])

    @bot.message_handler(content_types=["new_chat_members"])
    def verify_new_members(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            return
        for member in message.new_chat_members:
            if member.is_bot:
                continue
            try:
                bot.restrict_chat_member(
                    message.chat.id, member.id,
                    can_send_messages=False,
                    can_send_audios=False,
                    can_send_documents=False,
                    can_send_photos=False,
                    can_send_videos=False,
                    can_send_video_notes=False,
                    can_send_voice_notes=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(TEXT[lang_for(message)]["verify_btn"], callback_data=f"verify:{message.chat.id}:{member.id}"))
                bot.send_message(message.chat.id, TEXT[lang_for(message)]["verify"], reply_markup=markup)
            except Exception:
                logger.exception("new member verification failed")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("verify:"))
    def verify_callback(call):
        try:
            _, chat_id, user_id = call.data.split(":", 2)
            chat_id, user_id = int(chat_id), int(user_id)
            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, TEXT["en"]["verify_wrong"], show_alert=True)
                return
            bot.restrict_chat_member(chat_id, user_id, can_send_messages=True, can_send_audios=True,
                                     can_send_documents=True, can_send_photos=True, can_send_videos=True,
                                     can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
                                     can_send_other_messages=True, can_add_web_page_previews=True)
            bot.answer_callback_query(call.id, TEXT["en"]["verified"] if lang_for(call.message) == "en" else TEXT["fa"]["verified"])
            bot.edit_message_text(TEXT["en"]["verified"] if lang_for(call.message) == "en" else TEXT["fa"]["verified"], chat_id, call.message.message_id)
        except Exception:
            bot.answer_callback_query(call.id, TEXT["en"]["verify_fail"], show_alert=True)

    @bot.message_handler(content_types=["text"])
    def moderate(message: Message):
        if message.chat.type in {"group", "supergroup"}:
            moderation.handle(message)

    return bot


def run_bot() -> None:
    bot = build_bot()
    logger.info("XAI MASTER V3 starting Telegram polling")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
