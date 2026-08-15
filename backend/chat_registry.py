from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock


@dataclass
class ChatRecord:
    chat_id: int
    title: str
    chat_type: str
    username: str | None = None


class ChatRegistry:
    def __init__(self) -> None:
        self.path = Path(os.getenv("CHAT_REGISTRY_FILE", "data/miniapp_chats.json"))
        self._lock = Lock()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, chat_id: int, title: str, chat_type: str, username: str | None = None) -> None:
        with self._lock:
            data = self._load()
            data[str(chat_id)] = asdict(ChatRecord(chat_id, title, chat_type, username))
            self._save(data)

    def all(self) -> list[ChatRecord]:
        with self._lock:
            return [ChatRecord(**item) for item in self._load().values()]


registry = ChatRegistry()
