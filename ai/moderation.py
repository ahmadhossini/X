from __future__ import annotations

import re

LINK_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/)", re.IGNORECASE)


class ModerationEngine:
    def contains_link(self, text: str) -> bool:
        return bool(LINK_RE.search(text))

    def looks_like_flood(self, recent_message_count: int, threshold: int = 8) -> bool:
        return recent_message_count >= threshold

    def classify(self, text: str) -> str:
        if self.contains_link(text):
            return "link"
        return "normal"


moderation_engine = ModerationEngine()
