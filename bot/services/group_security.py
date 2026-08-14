from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from bot.services.group_settings_store import store

URL_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/)", re.I)
MENTION_RE = re.compile(r"@[A-Za-z0-9_]{3,}")
HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def settings_for(chat_id: int) -> dict[str, Any]:
    return asdict(store.get(chat_id))


def violation(message: Any, settings: dict[str, Any]) -> str | None:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    if settings.get("anti_link") and URL_RE.search(text):
        return "anti_link"
    if settings.get("mention_lock") and MENTION_RE.search(text):
        return "mention_lock"
    if settings.get("hashtag_lock") and HASHTAG_RE.search(text):
        return "hashtag_lock"
    if settings.get("phone_lock") and PHONE_RE.search(text):
        return "phone_lock"
    return None
