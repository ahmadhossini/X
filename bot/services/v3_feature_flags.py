from __future__ import annotations

FEATURES = {
    "anti_spam": "Anti Spam",
    "anti_flood": "Anti Flood",
    "anti_link": "Anti Link",
    "media_lock": "Media Lock",
    "forward_lock": "Forward Lock",
    "mention_lock": "Mention Lock",
    "hashtag_lock": "Hashtag Lock",
    "phone_lock": "Phone Lock",
    "profanity_filter": "Profanity Filter",
    "drug_filter": "Drug Filter",
    "nsfw_filter": "NSFW Filter",
    "force_join": "Force Join",
    "welcome": "Welcome",
    "goodbye": "Goodbye",
    "clean_deleted_accounts": "Deleted Account Cleanup",
    "clean_bots": "Bot Cleanup",
    "work_hours": "Work Hours",
    "global_mute": "Global Mute",
    "auto_pin": "Auto Pin",
    "auto_answer": "Auto Answer",
    "ai_chat": "AI Chat",
    "statistics": "Statistics",
}


def is_known_feature(name: str) -> bool:
    return name in FEATURES
