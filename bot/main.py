from __future__ import annotations

import logging
from typing import Optional

from telebot import TeleBot, types
from telebot.types import ChatPermissions, Message, User

from backend.chat_registry import registry
from backend.chat_stats import stats
from bot.services.group_settings_store import store
from bot.services.language_service import get_text
from bot.services.moderation import GroupModeration
from bot.services.user_language import get_user_language, set_user_language
from core.config import settings

logger = logging.getLogger(__name__)
SUPPORT_URL = "https://t.me/XAIMASTER_Official"


def lang_for(message: Message) -> str | None:
    return get_user_language(message.from_user.id)


def choose_language_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("• فارسی", callback_data="lang:fa"),
        types.InlineKeyboardButton("• English", callback_data="lang:en"),
    )
    return markup


def start_keyboard(lang: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    bot_username = getattr(settings, "bot_username", "") or "XAI_MASTER_BOT"
    miniapp_url = getattr(settings, "miniapp_url", "") or ""
    markup.add(types.InlineKeyboardButton(get_text(lang, "add_group"), url=f"https://t.me/{bot_username}?startgroup=true"))
    if miniapp_url:
        markup.add(types.InlineKeyboardButton(get_text(lang, "dashboard"), web_app=types.WebAppInfo(url=miniapp_url)))
    markup.add(types.InlineKeyboardButton(get_text(lang, "support"), url=SUPPORT_URL))
    return markup


def send_start(bot: TeleBot, chat_id: int, user: User, lang: str) -> None:
    name = user.first_name or user.username or "User"
    text = get_text(lang, "welcome", name=name) + "\n\n" + get_text(lang, "features") + "\n\n" + get_text(lang, "admin")
    bot.send_message(chat_id, text, reply_markup=start_keyboard(lang), parse_mode="HTML")


def _target_from_reply(message: Message) -> Optional[int]:
    return message.reply_to_message.from_user.id if message.reply_to_message and message.reply_to_message.from_user else None


def build_bot() -> TeleBot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    bot = TeleBot(settings.bot_token, parse_mode="HTML")
    moderation = GroupModeration(bot)

    def is_admin(message: Message) -> bool:
        if message.chat.type not in {"group", "supergroup"} or not message.from_user:
            return False
        try:
            return bot.get_chat_member(message.chat.id, message.from_user.id).status in {"creator", "administrator"}
        except Exception:
            return False

    def require_admin(message: Message) -> bool:
        if is_admin(message):
            return True
        bot.reply_to(message, get_text(lang_for(message) or "fa", "only_admin"))
        return False

    @bot.message_handler(commands=["start"])
    def start(message: Message):
        lang = lang_for(message)
        if not lang:
            return bot.send_message(
                message.chat.id,
                get_text("fa", "choose_language") + "\n\n" + get_text("en", "choose_language"),
                reply_markup=choose_language_keyboard(),
            )
        send_start(bot, message.chat.id, message.from_user, lang)

    @bot.message_handler(commands=["help"])
    def help_command(message: Message):
        send_start(bot, message.chat.id, message.from_user, lang_for(message) or "fa")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("lang:"))
    def language_callback(call):
        lang = call.data.split(":", 1)[1]
        if lang not in {"fa", "en"}:
            return bot.answer_callback_query(call.id, "Invalid language", show_alert=True)
        set_user_language(call.from_user.id, lang)
        bot.answer_callback_query(call.id)
        if call.message:
            send_start(bot, call.message.chat.id, call.from_user, lang)

    @bot.message_handler(content_types=["my_chat_member"])
    def chat_membership_update(message: Message):
        member = message.new_chat_member
        if not member or message.chat.type not in {"group", "supergroup", "channel"}:
            return
        if member.user and member.user.id == bot.get_me().id and member.status in {"administrator", "member"}:
            registry.upsert(message.chat.id, message.chat.title or "Untitled", message.chat.type, getattr(message.chat, "username", None))

    @bot.channel_post_handler(func=lambda message: True)
    def channel_post(message: Message):
        registry.upsert(message.chat.id, message.chat.title or "Untitled", "channel", getattr(message.chat, "username", None))

    @bot.message_handler(commands=["panel"])
    def panel(message: Message):
        lang = lang_for(message) or "fa"
        url = getattr(settings, "miniapp_url", "") or ""
        if not url:
            return bot.reply_to(message, get_text(lang, "panel_missing"))
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(get_text(lang, "dashboard"), web_app=types.WebAppInfo(url=url)))
        bot.reply_to(message, "<b>XAI MASTER V3</b>", reply_markup=markup)

    @bot.message_handler(commands=["market"])
    def market(message: Message):
        bot.reply_to(message, get_text(lang_for(message) or "fa", "market"))

    @bot.message_handler(commands=["warn"])
    def warn_command(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "برای اخطار باید به پیام کاربر Reply کنید.")
        cfg = store.get(message.chat.id)
        count = moderation.warn(message.chat.id, user_id, "اخطار مدیر")
        if count >= cfg.warning_limit:
            try:
                bot.restrict_chat_member(message.chat.id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=0)
                stats.record_action(message.chat.id, "restricted")
                return bot.reply_to(message, f"کاربر پس از رسیدن به {cfg.warning_limit} اخطار محدود شد.")
            except Exception:
                pass
        bot.reply_to(message, f"اخطار ثبت شد. تعداد اخطارها: {count}/{cfg.warning_limit}")

    @bot.message_handler(commands=["mute"])
    def mute_command(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "برای Mute باید به پیام کاربر Reply کنید.")
        try:
            bot.restrict_chat_member(message.chat.id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=0)
            stats.record_action(message.chat.id, "restricted")
            bot.reply_to(message, "کاربر Mute شد.")
        except Exception as exc:
            logger.exception("mute failed: %s", exc)
            bot.reply_to(message, "Mute انجام نشد.")

    @bot.message_handler(commands=["unmute", "رفع_محدودیت"])
    def unmute(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, get_text(lang_for(message) or "fa", "reply"))
        try:
            bot.restrict_chat_member(
                message.chat.id,
                user_id,
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
            bot.reply_to(message, get_text(lang_for(message) or "fa", "unmuted"))
        except Exception:
            bot.reply_to(message, get_text(lang_for(message) or "fa", "unmute_fail"))

    @bot.message_handler(commands=["ban"])
    def ban(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, get_text(lang_for(message) or "fa", "reply"))
        try:
            bot.ban_chat_member(message.chat.id, user_id)
            stats.record_action(message.chat.id, "banned")
            bot.reply_to(message, get_text(lang_for(message) or "fa", "banned"))
        except Exception:
            bot.reply_to(message, get_text(lang_for(message) or "fa", "ban_fail"))

    @bot.message_handler(commands=["unban"])
    def unban(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, get_text(lang_for(message) or "fa", "reply"))
        try:
            bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
            stats.record_action(message.chat.id, "unbanned")
            bot.reply_to(message, get_text(lang_for(message) or "fa", "unbanned"))
        except Exception:
            bot.reply_to(message, get_text(lang_for(message) or "fa", "unban_fail"))

    @bot.message_handler(commands=["kick"])
    def kick(message: Message):
        if not require_admin(message):
            return
        user_id = _target_from_reply(message)
        if not user_id:
            return bot.reply_to(message, "برای Kick باید به پیام کاربر Reply کنید.")
        try:
            bot.ban_chat_member(message.chat.id, user_id)
            bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
            stats.record_action(message.chat.id, "kicked")
            bot.reply_to(message, "کاربر Kick شد.")
        except Exception:
            bot.reply_to(message, "Kick انجام نشد.")

    @bot.message_handler(commands=["lock"])
    def lock(message: Message):
        if not require_admin(message):
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        feature = parts[1].strip() if len(parts) == 2 else "anti_link"
        try:
            store.set(message.chat.id, feature, True)
            bot.reply_to(message, f"قفل {feature} فعال شد.")
        except ValueError as exc:
            bot.reply_to(message, f"قابلیت ناشناخته: {exc}")

    @bot.message_handler(commands=["unlock"])
    def unlock(message: Message):
        if not require_admin(message):
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        feature = parts[1].strip() if len(parts) == 2 else "anti_link"
        try:
            store.set(message.chat.id, feature, False)
            bot.reply_to(message, f"قفل {feature} غیرفعال شد.")
        except ValueError as exc:
            bot.reply_to(message, f"قابلیت ناشناخته: {exc}")

    @bot.message_handler(commands=["settings"])
    def settings_command(message: Message):
        if not require_admin(message):
            return
        cfg = store.get(message.chat.id)
        active = [name for name, value in vars(cfg).items() if isinstance(value, bool) and value]
        bot.reply_to(message, "تنظیمات فعال:\n" + "\n".join(f"• {name}" for name in active))

    @bot.message_handler(commands=["filters"])
    def filters_command(message: Message):
        if not require_admin(message):
            return
        cfg = store.get(message.chat.id)
        items = [
            ("link", cfg.anti_link), ("username", cfg.mention_lock), ("hashtag", cfg.hashtag_lock),
            ("forward", cfg.forward_lock), ("phone", cfg.phone_lock), ("profanity", cfg.profanity_filter),
            ("drug", cfg.drug_filter), ("nsfw", cfg.nsfw_filter), ("flood", cfg.anti_flood),
        ]
        bot.reply_to(message, "فیلترها:\n" + "\n".join(f"• {name}: {'ON' if enabled else 'OFF'}" for name, enabled in items))

    @bot.message_handler(commands=["logs"])
    def logs_command(message: Message):
        if not require_admin(message):
            return
        snapshot = stats.get(message.chat.id)
        bot.reply_to(message, f"Messages: {snapshot['messages']}\nDeleted: {snapshot['deleted']}\nWarnings: {snapshot['warnings']}\nRestricted: {snapshot['restricted']}")

    @bot.message_handler(commands=["clean"])
    def clean_command(message: Message):
        if not require_admin(message):
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        try:
            count = max(1, min(100, int(parts[1]))) if len(parts) == 2 else 20
        except ValueError:
            count = 20
        deleted = 0
        for message_id in range(message.message_id, max(0, message.message_id - count), -1):
            try:
                if bot.delete_message(message.chat.id, message_id):
                    deleted += 1
            except Exception:
                continue
        bot.send_message(message.chat.id, f"{deleted} پیام پاک شد.")

    @bot.message_handler(content_types=["new_chat_members"])
    def verify_new_members(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            return
        registry.upsert(message.chat.id, message.chat.title or "Untitled", message.chat.type, getattr(message.chat, "username", None))
        lang = lang_for(message) or "fa"
        for member in message.new_chat_members:
            if member.is_bot:
                continue
            try:
                bot.restrict_chat_member(message.chat.id, member.id, can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(get_text(lang, "verify_btn"), callback_data=f"verify:{message.chat.id}:{member.id}"))
                bot.send_message(message.chat.id, get_text(lang, "verify"), reply_markup=markup)
            except Exception:
                logger.exception("new member verification failed")

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("verify:"))
    def verify_callback(call):
        try:
            _, chat_id_raw, user_id_raw = call.data.split(":", 2)
            chat_id, user_id = int(chat_id_raw), int(user_id_raw)
            lang = lang_for(call.message) or "fa"
            if call.from_user.id != user_id:
                return bot.answer_callback_query(call.id, get_text(lang, "verify_wrong"), show_alert=True)
            bot.restrict_chat_member(chat_id, user_id, can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
            bot.answer_callback_query(call.id, get_text(lang, "verified"))
            bot.edit_message_text(get_text(lang, "verified"), chat_id, call.message.message_id)
        except Exception:
            bot.answer_callback_query(call.id, get_text("fa", "verify_fail"), show_alert=True)

    @bot.message_handler(content_types=["text", "photo", "video", "animation", "audio", "voice", "document", "sticker", "video_note", "contact", "location", "venue", "poll"])
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
