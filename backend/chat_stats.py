from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


class ChatStats:
    def __init__(self) -> None:
        self.path = Path(os.getenv("CHAT_STATS_FILE", "data/chat_stats.json"))
        self.lock = Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_message(self, chat_id: int, user_id: int | None = None) -> None:
        with self.lock:
            data = self._load()
            item = data.setdefault(str(chat_id), {"messages": 0, "deleted": 0, "warnings": 0, "restricted": 0, "daily": {}})
            item["messages"] += 1
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            item.setdefault("daily", {}).setdefault(day, {"messages": 0, "deleted": 0, "warnings": 0})["messages"] += 1
            self._save(data)

    def record_action(self, chat_id: int, action: str) -> None:
        with self.lock:
            data = self._load()
            item = data.setdefault(str(chat_id), {"messages": 0, "deleted": 0, "warnings": 0, "restricted": 0, "daily": {}})
            item[action] = int(item.get(action, 0)) + 1
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            item.setdefault("daily", {}).setdefault(day, {"messages": 0, "deleted": 0, "warnings": 0})[action] = item["daily"].get(action, 0) + 1
            self._save(data)

    def get(self, chat_id: int) -> dict:
        with self.lock:
            item = self._load().get(str(chat_id), {})
        daily = item.get("daily", {})
        days = sorted(daily)[-14:]
        return {
            "messages": int(item.get("messages", 0)),
            "deleted": int(item.get("deleted", 0)),
            "warnings": int(item.get("warnings", 0)),
            "restricted": int(item.get("restricted", 0)),
            "chart": [{"date": day, **daily[day]} for day in days],
        }


stats = ChatStats()
