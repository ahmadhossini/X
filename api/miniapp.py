from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from billing.service import BillingError, estimate_task_credits, reserve_task_credits
from code_agent.github_app import GitHubAppError, github_app_get, github_app_get_installation
from core.config import settings
from database.models import GitHubInstallation, Task, User
from database.session import SessionLocal

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])

INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60
SUPPORTED_LANGUAGES = {"fa", "en", "hi"}


class TaskRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=255)
    request: str = Field(min_length=3, max_length=4000)
    language: str | None = Field(default=None, max_length=8)


class LanguageRequest(BaseModel):
    language: str = Field(min_length=2, max_length=8)


def _telegram_user(init_data: str) -> dict:
    if not init_data or len(init_data) > 8192:
        raise HTTPException(status_code=401, detail="Invalid Telegram session")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        supplied_hash = pairs.pop("hash", "")
        if not supplied_hash or len(supplied_hash) != 64:
            raise ValueError
        data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
        expected_hash = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, supplied_hash):
            raise ValueError
        auth_date = int(pairs.get("auth_date", "0"))
        if auth_date <= 0 or abs(int(time.time()) - auth_date) > INIT_DATA_MAX_AGE_SECONDS:
            raise ValueError
        user = json.loads(pairs.get("user", "{}"))
        telegram_id = int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid Telegram session")
    return {"id": telegram_id, "language_code": user.get("language_code")}


def _auth_user(init_data: str) -> User:
    tg = _telegram_user(init_data)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == tg["id"]))
        if user is None:
            language = tg.get("language_code") or "en"
            if language not in SUPPORTED_LANGUAGES:
                language = "en"
            user = User(telegram_id=tg["id"], language=language)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user


def _init_data(authorization: str | None, x_telegram_init_data: str | None) -> str:
    value = x_telegram_init_data or ""
    if not value and authorization and authorization.lower().startswith("tma "):
        value = authorization[4:].strip()
    return value


@router.get("/me")
async def me(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        current = db.scalar(select(User).where(User.id == user.id))
        if not current:
            raise HTTPException(status_code=401, detail="User session not found")
        installation = db.scalar(select(GitHubInstallation).where(GitHubInstallation.user_id == current.id, GitHubInstallation.active.is_(True)).order_by(GitHubInstallation.updated_at.desc()))
        result = {
            "telegram_id": current.telegram_id,
            "language": current.language if current.language in SUPPORTED_LANGUAGES else "en",
            "plan": current.plan,
            "credits": current.credits,
            "github_connected": installation is not None,
            "github_login": installation.github_login if installation else None,
            "installation_id": installation.installation_id if installation else None,
            "github_avatar_url": None,
            "ton_pro_price_ton": settings.ton_pro_price_nano_ton / 1_000_000_000,
        }
    if installation:
        try:
            info = await github_app_get_installation(installation.installation_id)
            account = info.get("account") or {}
            result["github_login"] = account.get("login") or result["github_login"]
            result["github_avatar_url"] = account.get("avatar_url")
        except GitHubAppError:
            pass
    return result
