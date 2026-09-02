from __future__ import annotations

import os

from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    bot_username: str = os.getenv("BOT_USERNAME", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    github_app_id: str = os.getenv("GITHUB_APP_ID", "")
    github_app_slug: str = os.getenv("GITHUB_APP_SLUG", "")
    github_app_private_key: str = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    github_connect_secret: str = os.getenv("GITHUB_CONNECT_SECRET", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    code_agent_api_key: str = os.getenv("CODE_AGENT_API_KEY", "")
    telegram_admin_ids: tuple[int, ...] = tuple(
        int(value.strip())
        for value in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
        if value.strip().lstrip("-").isdigit()
    )
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./xai_master.db")


settings = Settings()
