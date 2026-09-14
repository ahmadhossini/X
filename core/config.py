from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


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
    toncenter_api_key: str = os.getenv("TONCENTER_API_KEY", "")
    ton_payment_address: str = os.getenv("TON_PAYMENT_ADDRESS", "")
    ton_usdt_master_address: str = os.getenv("TON_USDT_MASTER_ADDRESS", "")
    ton_payment_expiry_minutes: int = _positive_int("TON_PAYMENT_EXPIRY_MINUTES", 30, 5, 120)
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    miniapp_url: str = os.getenv("MINIAPP_URL", "").rstrip("/")
    code_agent_api_key: str = os.getenv("CODE_AGENT_API_KEY", "")
    telegram_admin_ids: tuple[int, ...] = tuple(
        int(value.strip())
        for value in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
        if value.strip().lstrip("-").isdigit()
    )
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./xai_master.db")
    code_agent_workers: int = _positive_int("CODE_AGENT_WORKERS", 20, 2, 100)
    code_agent_queue_size: int = _positive_int("CODE_AGENT_QUEUE_SIZE", 1000, 50, 10000)


settings = Settings()
