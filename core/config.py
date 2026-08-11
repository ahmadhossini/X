from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int_set(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(item.strip()) for item in value.split(",") if item.strip().isdigit()}


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    admin_ids: set[int] = field(default_factory=set)
    sponsor_channel: str = os.getenv("SPONSOR_CHANNEL", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./xai_master.db")
    market_cache_seconds: int = int(os.getenv("MARKET_CACHE_SECONDS", "60"))
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

    def __post_init__(self) -> None:
        object.__setattr__(self, "admin_ids", _int_set(os.getenv("ADMIN_IDS")))


settings = Settings()
