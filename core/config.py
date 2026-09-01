from __future__ import annotations

import os

from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    github_app_id: str = os.getenv("GITHUB_APP_ID", "")
    github_app_private_key: str = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
    github_app_installation_id: str = os.getenv("GITHUB_INSTALLATION_ID", "")
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    code_agent_api_key: str = os.getenv("CODE_AGENT_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./xai_master.db")


settings = Settings()
