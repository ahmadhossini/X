from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

DEFAULTS: dict[str, Any] = {
    "anti_spam": True,
    "anti_flood": True,
    "anti_link": True,
    "lock_media": False,
    "lock_forward": False,
    "lock_mentions": False,
    "lock_hashtags": False,
    "lock_phone_numbers": False,
    "force_join": False,
    "welcome": True,
    "goodbye": True,
    "remove_deleted_accounts": False,
    "remove_bots": False,
    "work_hours": False,
    "global_mute": False,
    "auto_pin": False,
    "bad_words_filter": True,
    "drug_filter": True,
    "nsfw_filter": True,
    "auto_answer": False,
    "ai_chat": True,
    "statistics": True,
}

FILE = Path(os.getenv("GROUP_SETTINGS_FILE", "data/group_settings.json"))
_LOCK = Lock()


def _load() -> dict[str, dict[str, Any]]:
    if not FILE.exists():
        return {}
    try:
        value = json.loads(FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(value: dict[str, dict[str, Any]]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_group_settings(chat_id: int) -> dict[str, Any]:
    with _LOCK:
        all_settings = _load()
        current = dict(DEFAULTS)
        current.update(all_settings.get(str(chat_id), {}))
        return current


def set_group_setting(chat_id: int, key: str, enabled: bool) -> dict[str, Any]:
    if key not in DEFAULTS:
        raise KeyError(key)
    with _LOCK:
        all_settings = _load()
        current = dict(DEFAULTS)
        current.update(all_settings.get(str(chat_id), {}))
        current[key] = bool(enabled)
        all_settings[str(chat_id)] = current
        _save(all_settings)
        return current
