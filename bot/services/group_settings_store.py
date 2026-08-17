from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class GroupSettings:
    # Text/security rules
    anti_spam: bool = True
    anti_flood: bool = True
    anti_link: bool = True
    forward_lock: bool = True
    mention_lock: bool = True
    hashtag_lock: bool = True
    phone_lock: bool = False
    profanity_filter: bool = True
    drug_filter: bool = True
    nsfw_filter: bool = True

    # Media locks
    photo_lock: bool = False
    video_lock: bool = False
    document_lock: bool = False
    audio_lock: bool = False
    voice_lock: bool = False
    video_note_lock: bool = False
    sticker_lock: bool = False
    animation_lock: bool = False
    poll_lock: bool = False
    location_lock: bool = False
    contact_lock: bool = False

    # Member/group automation
    force_join: bool = False
    welcome: bool = True
    goodbye: bool = True
    clean_deleted_accounts: bool = True
    clean_bots: bool = False
    work_hours: bool = False
    global_mute: bool = False
    auto_pin: bool = False
    auto_answer: bool = False
    ai_chat: bool = True
    statistics: bool = True

    # Moderation policy
    warning_limit: int = 3
    flood_messages: int = 8
    flood_window_seconds: int = 10
    flood_mute_seconds: int = 60
    repeat_message_limit: int = 3


# Backward-compatible aliases accepted by the API/UI from older V3 builds.
ALIASES: dict[str, str] = {
    "media_lock": "photo_lock",
    "lock_media": "photo_lock",
    "lock_forward": "forward_lock",
    "lock_mentions": "mention_lock",
    "lock_hashtags": "hashtag_lock",
    "lock_phone_numbers": "phone_lock",
    "bad_words_filter": "profanity_filter",
    "banned_words": "profanity_filter",
}

FILE = Path(os.getenv("GROUP_SETTINGS_FILE", "data/group_settings.json"))
_LOCK = Lock()


class GroupSettingsStore:
    def _load(self) -> dict[str, dict[str, Any]]:
        if not FILE.exists():
            return {}
        try:
            value = json.loads(FILE.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, value: dict[str, dict[str, Any]]) -> None:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(FILE)

    def get(self, chat_id: int) -> GroupSettings:
        with _LOCK:
            raw = self._load().get(str(chat_id), {})
        values = asdict(GroupSettings())
        if isinstance(raw, dict):
            for key, value in raw.items():
                canonical = ALIASES.get(key, key)
                if canonical in values:
                    values[canonical] = value
        return GroupSettings(**values)

    def set(self, chat_id: int, feature: str, value: Any) -> GroupSettings:
        feature = ALIASES.get(feature, feature)
        defaults = asdict(GroupSettings())
        if feature not in defaults:
            raise ValueError(f"Unknown group feature: {feature}")
        if isinstance(defaults[feature], bool):
            value = bool(value)
        elif isinstance(defaults[feature], int):
            value = max(0, int(value))
        with _LOCK:
            data = self._load()
            current = asdict(self.get(chat_id))
            current[feature] = value
            data[str(chat_id)] = current
            self._save(data)
        return GroupSettings(**current)


store = GroupSettingsStore()
