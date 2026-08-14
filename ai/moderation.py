from __future__ import annotations

import re

LINK_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/|tg://)", re.IGNORECASE)
MENTION_RE = re.compile(r"@[A-Za-z0-9_]{3,}")
HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")

# Keep these lists deliberately conservative. They are policy hooks, not a
# claim that every occurrence is harmful; groups can turn each filter off.
PROFANITY_TERMS = {
    "کسکش", "کونی", "جنده", "حرومزاده", "fuck", "motherfucker", "bitch"
}
DRUG_TERMS = {
    "کوکائین", "کراک", "شیشه", "هروئین", "تریاک", "ماریجوانا", "cocaine", "heroin", "meth"
}
NSFW_TERMS = {
    "porn", "porno", "pornography", "سکس", "پورن"
}


class ModerationEngine:
    def contains_link(self, text: str) -> bool:
        return bool(LINK_RE.search(text))

    def contains_mention(self, text: str) -> bool:
        return bool(MENTION_RE.search(text))

    def contains_hashtag(self, text: str) -> bool:
        return bool(HASHTAG_RE.search(text))

    def contains_phone(self, text: str) -> bool:
        return bool(PHONE_RE.search(text))

    @staticmethod
    def _contains_term(text: str, terms: set[str]) -> bool:
        normalized = " ".join(text.casefold().split())
        return any(term.casefold() in normalized for term in terms)

    def contains_profanity(self, text: str) -> bool:
        return self._contains_term(text, PROFANITY_TERMS)

    def contains_drug_content(self, text: str) -> bool:
        return self._contains_term(text, DRUG_TERMS)

    def contains_nsfw_content(self, text: str) -> bool:
        return self._contains_term(text, NSFW_TERMS)

    def looks_like_flood(self, recent_message_count: int, threshold: int = 8) -> bool:
        return recent_message_count >= threshold

    def classify(self, text: str) -> str:
        if self.contains_link(text):
            return "link"
        if self.contains_drug_content(text):
            return "drug"
        if self.contains_nsfw_content(text):
            return "nsfw"
        if self.contains_profanity(text):
            return "profanity"
        return "normal"


moderation_engine = ModerationEngine()
