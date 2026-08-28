from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = Path(os.getenv("USER_LANGUAGE_FILE", str(PROJECT_ROOT / "data" / "user_languages.json")))
_LOCK = Lock()
_CACHE: dict[str, str] | None = None
_CHAT_LANG: dict[int, str] = {}
_CALLBACK_LANG: dict[str, str] = {}
_PATCHED = False


def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not DATA_FILE.exists():
        _CACHE = {}
        return _CACHE
    try:
        value = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        _CACHE = value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        _CACHE = {}
    return _CACHE


def _save(data: dict[str, str]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = DATA_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(DATA_FILE)


def get_user_language(user_id: int) -> str | None:
    with _LOCK:
        return _load().get(str(user_id))


def set_user_language(user_id: int, language: str) -> None:
    global _CACHE
    if language not in {"fa", "en"}:
        raise ValueError("Unsupported language")
    with _LOCK:
        data = _load()
        data[str(user_id)] = language
        _CACHE = data
        _save(data)


def _load_locales() -> tuple[dict[str, str], dict[str, str]]:
    base = PROJECT_ROOT / "bot" / "locales"
    result = []
    for lang in ("fa", "en"):
        try:
            result.append(json.loads((base / f"{lang}.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            result.append({})
    return result[0], result[1]


def _translate(text: str, language: str) -> str:
    if not text or language not in {"fa", "en"}:
        return text
    fa, en = _load_locales()
    source, target = (fa, en) if language == "en" else (en, fa)
    for key, value in source.items():
        if isinstance(value, str) and text == value:
            return target.get(key, text)

    exact = {
        "Reply to a user message first.": ("لطفاً روی پیام کاربر ریپلای کنید و دستور را دوباره بفرستید.", "Reply to a user message first."),
        "Reply to user message.": ("لطفاً روی پیام کاربر ریپلای کنید.", "Reply to user message."),
        "Warning added. Total warnings: ": ("هشدار ثبت شد. تعداد هشدارها: ", "Warning added. Total warnings: "),
        "Warning failed.": ("ثبت هشدار انجام نشد.", "Warning failed."),
        "Ban failed.": ("نتوانستم کاربر را مسدود کنم.", "Ban failed."),
        "Unban failed.": ("نتوانستم مسدودی کاربر را بردارم.", "Unban failed."),
        "User banned.": ("کاربر مسدود شد.", "User banned."),
        "User unbanned.": ("مسدودی کاربر برداشته شد.", "User unbanned."),
        "User unmuted.": ("محدودیت کاربر برداشته شد.", "User unmuted."),
        "Please verify you are human.": ("لطفاً برای ادامه تأیید کنید که انسان هستید.", "Please verify you are human."),
        "Verify": ("تأیید", "Verify"),
        "Not for you": ("این تأیید برای شما نیست.", "Not for you"),
        "Verified": ("تأیید شد.", "Verified"),
        "Verification failed": ("تأیید انجام نشد.", "Verification failed"),
        "Invalid language": ("زبان انتخاب‌شده معتبر نیست.", "Invalid language"),
        "• ادامه در پیام خصوصی": ("• ادامه در پیام خصوصی", "• Continue in Private Chat"),
        "• باز کردن پنل مدیریت": ("• باز کردن پنل مدیریت", "• Open Management Panel"),
    }
    if text in exact:
        fa_text, en_text = exact[text]
        return en_text if language == "en" else fa_text

    patterns = [
        (r"^Warning added\. Total warnings: (.+)$", lambda m: (f"هشدار ثبت شد. تعداد هشدارها: {m.group(1)}", f"Warning added. Total warnings: {m.group(1)}")),
        (r"^این قابلیت فقط داخل گروه قابل استفاده است\.$", lambda m: (text, "This feature is available only inside a group.")),
        (r"^برای حذف پیام‌ها، XAI MASTER باید در این گروه دسترسی «حذف پیام‌ها» داشته باشد\.$", lambda m: (text, "XAI MASTER needs permission to delete messages in this group.")),
        (r"^برای حذف پیام‌ها، XAI MASTER باید دسترسی «حذف پیام‌ها» داشته باشد\.$", lambda m: (text, "XAI MASTER needs permission to delete messages.")),
        (r"^فرمت: /autodelete 10m\\nنمونه‌ها: 30s، 10m، 1h، 1d\\nخاموش کردن: /autodelete off$", lambda m: (text, "Format: /autodelete 10m\\nExamples: 30s, 10m, 1h, 1d\\nDisable: /autodelete off")),
        (r"^حذف خودکار پیام‌ها خاموش شد\.$", lambda m: (text, "Automatic message deletion has been disabled.")),
        (r"^حذف خودکار فعال شد\. پیام کاربران بعد از (.+) حذف می‌شود\.$", lambda m: (f"حذف خودکار فعال شد. پیام کاربران بعد از {m.group(1)} حذف می‌شود.", f"Automatic deletion is enabled. User messages will be deleted after {m.group(1)}.")),
        (r"^زمان نامعتبر است\. از نمونه‌هایی مثل (.+) استفاده کنید\.$", lambda m: (text, "The entered time is invalid. Use examples such as 30s, 10m, 1h or 1d.")),
        (r"^تعداد پیام باید بین 1 تا 100 باشد\.\\nمثال: /حذف 10پیام$", lambda m: (text, "The message count must be between 1 and 100.\\nExample: /delete 10")),
        (r"^(.+) پیام حذف شد\.$", lambda m: (f"{m.group(1)} پیام حذف شد.", f"{m.group(1)} messages deleted.")),
        (r"^پیامی برای حذف پیدا نشد\. برای حذف یک پیام مشخص، روی همان پیام ریپلای کنید و /delete بفرستید\.$", lambda m: (text, "No messages were found to delete. To delete a specific message, reply to it and send /delete.")),
        (r"^در حال حاضر نتوانستم پاسخ بدهم\. لطفاً چند لحظه بعد دوباره تلاش کنید\.$", lambda m: (text, "I could not answer right now. Please try again in a moment.")),
        (r"^سرویس هوش مصنوعی موقتاً در دسترس نیست\.$", lambda m: (text, "The AI service is temporarily unavailable.")),
        (r"^سهمیه روزانه ۲۰ درخواست شما تمام شده است\. فردا دوباره می‌توانید از XAI MASTER استفاده کنید\.$", lambda m: (text, "Your daily limit of 20 requests has been reached. You can use XAI MASTER again tomorrow.")),
        (r"^سهمیه روزانه ۵ درخواست شما در این گروه تمام شده است\.\\n\\nبرای ادامه گفتگو، به پیام خصوصی XAI MASTER بروید\.$", lambda m: (text, "Your daily limit of 5 requests in this group has been reached.\\n\\nContinue the conversation in XAI MASTER's private chat.")),
        (r"^برای تنظیمات کامل گروه از /panel استفاده کنید\.$", lambda m: (text, "Use /panel for the complete group settings.")),
    ]
    for pattern, builder in patterns:
        match = re.match(pattern, text, flags=re.DOTALL)
        if match:
            fa_text, en_text = builder(match)
            return en_text if language == "en" else fa_text
    return text


def _localize_markup(markup, language: str):
    if markup is None:
        return markup
    for row_name in ("keyboard", "inline_keyboard"):
        rows = getattr(markup, row_name, None)
        if rows:
            for row in rows:
                for button in row:
                    if getattr(button, "text", None):
                        button.text = _translate(button.text, language)
    return markup


def _patch_telebot() -> None:
    global _PATCHED
    if _PATCHED:
        return
    try:
        from telebot import TeleBot
    except Exception:
        return

    original_process = TeleBot.process_new_updates
    original_reply = TeleBot.reply_to
    original_send = TeleBot.send_message
    original_answer = TeleBot.answer_callback_query
    original_edit = TeleBot.edit_message_text

    def remember_update(update) -> None:
        message = getattr(update, "message", None) or getattr(update, "edited_message", None)
        if message is not None and getattr(message, "chat", None) is not None and getattr(message, "from_user", None) is not None:
            lang = get_user_language(message.from_user.id)
            if lang:
                _CHAT_LANG[message.chat.id] = lang
        callback = getattr(update, "callback_query", None)
        if callback is not None and getattr(callback, "message", None) is not None and getattr(callback, "from_user", None) is not None:
            lang = get_user_language(callback.from_user.id)
            if lang:
                _CHAT_LANG[callback.message.chat.id] = lang
                _CALLBACK_LANG[str(callback.id)] = lang

    def process(self, updates):
        for update in updates:
            remember_update(update)
        return original_process(self, updates)

    def reply(self, message, text, *args, **kwargs):
        user = getattr(message, "from_user", None)
        if user is not None:
            lang = get_user_language(user.id) or _CHAT_LANG.get(message.chat.id, "fa")
            _CHAT_LANG[message.chat.id] = lang
            text = _translate(text, lang)
            if "reply_markup" in kwargs:
                kwargs["reply_markup"] = _localize_markup(kwargs["reply_markup"], lang)
        return original_reply(self, message, text, *args, **kwargs)

    def send(self, chat_id, text, *args, **kwargs):
        lang = _CHAT_LANG.get(chat_id)
        if lang:
            text = _translate(text, lang)
            if "reply_markup" in kwargs:
                kwargs["reply_markup"] = _localize_markup(kwargs["reply_markup"], lang)
        return original_send(self, chat_id, text, *args, **kwargs)

    def answer(self, callback_query_id, text=None, *args, **kwargs):
        if text:
            text = _translate(text, _CALLBACK_LANG.get(str(callback_query_id), "fa"))
        return original_answer(self, callback_query_id, text, *args, **kwargs)

    def edit(self, text, chat_id, message_id, *args, **kwargs):
        lang = _CHAT_LANG.get(chat_id)
        if lang:
            text = _translate(text, lang)
        return original_edit(self, text, chat_id, message_id, *args, **kwargs)

    TeleBot.process_new_updates = process
    TeleBot.reply_to = reply
    TeleBot.send_message = send
    TeleBot.answer_callback_query = answer
    TeleBot.edit_message_text = edit
    _PATCHED = True


_patch_telebot()
