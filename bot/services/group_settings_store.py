from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

@dataclass
class GroupSettings:
    anti_spam: bool = True
    anti_flood: bool = True
    anti_link: bool = True
    media_lock: bool = False
    forward_lock: bool = True
    mention_lock: bool = True
    hashtag_lock: bool = True
    phone_lock: bool = False
    profanity_filter: bool = True
    drug_filter: bool = True
    nsfw_filter: bool = True
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

class GroupSettingsStore:
    def __init__(self) -> None:
        self.path = Path(os.getenv("GROUP_SETTINGS_FILE", "data/group_settings.json"))
        self._lock = Lock()
    def _load(self) -> dict:
        if not self.path.exists(): return {}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return {}
    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    def get(self, chat_id: int) -> GroupSettings:
        with self._lock:
            raw = self._load().get(str(chat_id), {})
        values = asdict(GroupSettings()); values.update(raw)
        return GroupSettings(**values)
    def set(self, chat_id: int, feature: str, enabled: bool) -> GroupSettings:
        settings = self.get(chat_id)
        if not hasattr(settings, feature): raise ValueError(f"Unknown group feature: {feature}")
        setattr(settings, feature, bool(enabled))
        with self._lock:
            data = self._load(); data[str(chat_id)] = asdict(settings); self._save(data)
        return settings

store = GroupSettingsStore()
