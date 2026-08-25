from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock


@dataclass
class GroupSettings:
    settings_version: int = 2
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
    force_join_count: int = 0
    force_join_channels: list[str] = field(default_factory=list)
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
        project_root = Path(__file__).resolve().parents[2]
        self.path = Path(os.getenv("GROUP_SETTINGS_FILE", str(project_root / "data" / "group_settings.json")))
        self._lock = Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.path.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.path)

    def get(self, chat_id: int) -> GroupSettings:
        chat_key = str(chat_id)
        with self._lock:
            data = self._load()
            raw = data.get(chat_key, {})

            values = asdict(GroupSettings())
            if isinstance(raw, dict):
                values.update(raw)

            # Migrate old groups once. In V1 these three protections were
            # disabled by default, so existing groups kept false in storage.
            # Version 2 makes the core moderation protections active unless
            # the administrator explicitly turns them off afterwards.
            if not isinstance(raw, dict) or int(raw.get("settings_version", 0) or 0) < 2:
                values["settings_version"] = 2
                values["forward_lock"] = True
                values["mention_lock"] = True
                values["hashtag_lock"] = True
                data[chat_key] = values
                self._save(data)

        if not isinstance(values.get("force_join_channels"), list):
            values["force_join_channels"] = []
        values["force_join_count"] = int(values.get("force_join_count", len(values["force_join_channels"])))
        return GroupSettings(**values)

    def touch(self, chat_id: int) -> GroupSettings:
        settings = self.get(chat_id)
        with self._lock:
            data = self._load()
            data.setdefault(str(chat_id), asdict(settings))
            self._save(data)
        return settings

    def set(self, chat_id: int, feature: str, enabled: bool) -> GroupSettings:
        settings = self.get(chat_id)
        if not hasattr(settings, feature):
            raise ValueError(f"Unknown group feature: {feature}")
        setattr(settings, feature, bool(enabled))
        with self._lock:
            data = self._load()
            data[str(chat_id)] = asdict(settings)
            self._save(data)
        return settings

    def update_config(
        self,
        chat_id: int,
        *,
        force_join_count: int | None = None,
        force_join_channels: list[str] | None = None,
    ) -> GroupSettings:
        settings = self.get(chat_id)
        if force_join_channels is not None:
            channels = []
            for value in force_join_channels:
                value = str(value).strip()
                if value and value not in channels:
                    channels.append(value)
            settings.force_join_channels = channels
            if force_join_count is None:
                force_join_count = len(channels)
        if force_join_count is not None:
            settings.force_join_count = max(0, min(int(force_join_count), 20))
        if settings.force_join_count > 0:
            settings.force_join = True
        elif force_join_count is not None and settings.force_join_count == 0:
            settings.force_join = False

        with self._lock:
            data = self._load()
            data[str(chat_id)] = asdict(settings)
            self._save(data)
        return settings


store = GroupSettingsStore()
