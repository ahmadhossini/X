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


def _csv_ints(*names: str) -> tuple[int, ...]:
    for name in names:
        raw = os.getenv(name, "").strip()
        if raw:
            return tuple(int(v.strip()) for v in raw.split(",") if v.strip().lstrip("-").isdigit())
    return ()


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
    miniapp_url: str = os.getenv("MINIAPP_URL", "").rstrip("/")
    code_agent_api_key: str = os.getenv("CODE_AGENT_API_KEY", "")
    telegram_admin_ids: tuple[int, ...] = _csv_ints("TELEGRAM_ADMIN_IDS", "ADMIN_IDS")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./xai_master.db")
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    code_agent_workers: int = _positive_int("CODE_AGENT_WORKERS", 4, 1, 50)
    code_agent_queue_size: int = _positive_int("CODE_AGENT_QUEUE_SIZE", 1000, 50, 10000)
    code_agent_job_timeout_seconds: int = _positive_int("CODE_AGENT_JOB_TIMEOUT_SECONDS", 1800, 60, 7200)
    code_agent_stale_task_seconds: int = _positive_int("CODE_AGENT_STALE_TASK_SECONDS", 2100, 120, 14400)
    free_monthly_credits: int = _positive_int("FREE_MONTHLY_CREDITS", 15, 1, 1000)
    pro_monthly_credits: int = _positive_int("PRO_MONTHLY_CREDITS", 500, 10, 100000)
    team_monthly_credits: int = _positive_int("TEAM_MONTHLY_CREDITS", 2000, 10, 1000000)
    ton_wallet_address: str = os.getenv("TON_WALLET_ADDRESS", "").strip()
    ton_network: str = os.getenv("TON_NETWORK", "mainnet").strip().lower()
    stars_pro_amount: int = _positive_int("STARS_PRO_AMOUNT", 600, 1, 1000000)
    stars_team_amount: int = _positive_int("STARS_TEAM_AMOUNT", 1450, 1, 1000000)
    toncenter_api_key: str = (
        os.getenv("TONCENTER_API_KEY", "").strip()
        or os.getenv("TON_API_KEY", "").strip()
    )


settings = Settings()
