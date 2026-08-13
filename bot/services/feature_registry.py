from __future__ import annotations

FEATURES = {
    "security": [
        "anti_spam",
        "anti_flood",
        "anti_link",
        "lock_media",
        "lock_forward",
        "lock_mentions",
        "lock_hashtags",
        "lock_phone_numbers",
        "bad_words_filter",
        "drug_filter",
        "nsfw_filter",
    ],
    "members": [
        "force_join",
        "welcome",
        "goodbye",
        "remove_deleted_accounts",
        "remove_bots",
    ],
    "moderation": [
        "work_hours",
        "global_mute",
        "auto_pin",
    ],
    "ai": [
        "auto_answer",
        "ai_chat",
        "statistics",
    ],
}

COMMANDS = {
    "ban", "unban", "mute", "unmute", "warn", "clean", "lock", "unlock",
    "settings", "security", "stats", "pin", "unpin", "forcejoin", "workhours",
    "globalmute", "welcome", "goodbye",
}
