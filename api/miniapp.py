from __future__ import annotations

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

# existing auth helpers are preserved

def _telegram_user(init_data: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    supplied_hash = pairs.pop("hash", "")
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash):
        raise HTTPException(401, "Invalid Telegram session")
    data = json.loads(pairs.get("user", "{}"))
    if abs(int(time.time()) - int(pairs.get("auth_date", 0))) > INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(401, "Expired Telegram session")
    return {"id": int(data["id"]), "language_code": data.get("language_code")}


def _init_data(authorization, x_telegram_init_data):
    return x_telegram_init_data or (authorization[4:].strip() if authorization and authorization.lower().startswith("tma ") else "")


def _auth_user(init_data):
    tg = _telegram_user(init_data)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == tg["id"]))
        if not user:
            user = User(telegram_id=tg["id"], language=tg.get("language_code") or "en")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

@router.get("/me")
async def me(authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    return {"telegram_id": user.telegram_id, "language": user.language, "plan": user.plan, "credits": user.credits, "ton_pro_price_ton": settings.ton_pro_price_nano_ton / 1_000_000_000}

@router.get("/repos")
async def repos(authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        installation = db.scalar(select(GitHubInstallation).where(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True)))
    if not installation:
        raise HTTPException(409, "GitHub not connected")
    data = await github_app_get("/installation/repositories?per_page=100", installation.installation_id)
    return {"repositories": data.get("repositories", [])}

@router.post("/language")
def language(payload: LanguageRequest, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        current = db.scalar(select(User).where(User.id == user.id))
        current.language = payload.language
        db.commit()
    return {"language": payload.language}

@router.post("/task")
def task(payload: TaskRequest, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    try:
        reservation = reserve_task_credits(user.telegram_id, payload.repository, payload.request, estimate_task_credits(payload.request), model=settings.gemini_model, chat_id=user.telegram_id, language=payload.language or user.language)
    except BillingError as exc:
        raise HTTPException(402, str(exc))
    return {"task_id": reservation.task_id, "status": "queued"}

@router.get("/task/{task_id}")
def task_status(task_id: str, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task:
        raise HTTPException(404, "Task not found")
    return {"task_id": task.id, "status": task.status}
