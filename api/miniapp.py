from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.workers.queue import enqueue_coding_task
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
    with SessionLocal() as db:
        installation = db.scalar(select(GitHubInstallation).where(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True)).order_by(GitHubInstallation.updated_at.desc()))
    github_connected = installation is not None
    github_login = None
    github_avatar_url = None
    if installation:
        try:
            installation_data = await github_app_get_installation(installation.installation_id)
            account = installation_data.get("account") or {}
            github_login = account.get("login") or installation.github_login
            github_avatar_url = account.get("avatar_url")
        except GitHubAppError:
            github_login = installation.github_login
    return {
        "telegram_id": user.telegram_id,
        "language": user.language,
        "plan": user.plan,
        "credits": user.credits,
        "github_connected": github_connected,
        "github_login": github_login,
        "github_avatar_url": github_avatar_url,
        "stars_pro_amount": settings.stars_pro_amount,
        "stars_team_amount": settings.stars_team_amount,
        "pro_price_usd": 12,
        "team_price_usd": 29,
    }


@router.get("/repos")
async def repos(authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        installation = db.scalar(select(GitHubInstallation).where(GitHubInstallation.user_id == user.id, GitHubInstallation.active.is_(True)).order_by(GitHubInstallation.updated_at.desc()))
    if not installation:
        raise HTTPException(409, "GitHub not connected")
    repositories: list[dict] = []
    try:
        for page in range(1, 11):
            data = await github_app_get(f"/installation/repositories?per_page=100&page={page}", installation.installation_id)
            page_items = data.get("repositories", [])
            if not isinstance(page_items, list):
                raise GitHubAppError("GitHub returned an invalid repositories response")
            repositories.extend(item for item in page_items if isinstance(item, dict))
            if len(page_items) < 100:
                break
    except GitHubAppError as exc:
        raise HTTPException(502, str(exc)) from exc
    normalized = [{
        "id": repo.get("id"),
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "description": repo.get("description"),
        "private": bool(repo.get("private")),
        "default_branch": repo.get("default_branch") or "main",
        "owner_login": (repo.get("owner") or {}).get("login"),
        "owner_avatar_url": (repo.get("owner") or {}).get("avatar_url"),
        "visibility": "private" if repo.get("private") else "public",
        "language": repo.get("language"),
        "stargazers_count": repo.get("stargazers_count", 0),
        "forks_count": repo.get("forks_count", 0),
        "open_issues_count": repo.get("open_issues_count", 0),
        "updated_at": repo.get("updated_at"),
    } for repo in repositories if repo.get("full_name")]
    normalized.sort(key=lambda repo: repo.get("updated_at") or "", reverse=True)
    return {"repositories": normalized}


@router.post("/language")
def language(payload: LanguageRequest, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, "Unsupported language")
    with SessionLocal() as db:
        current = db.scalar(select(User).where(User.id == user.id))
        current.language = payload.language
        db.commit()
    return {"language": payload.language}


@router.post("/task")
async def task(payload: TaskRequest, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    try:
        reservation = reserve_task_credits(user.telegram_id, payload.repository, payload.request, estimate_task_credits(payload.request), model=settings.gemini_model, chat_id=user.telegram_id, language=payload.language or user.language)
    except BillingError as exc:
        raise HTTPException(402, str(exc))
    try:
        await enqueue_coding_task(reservation.task_id)
    except Exception as exc:
        # Keep the durable DB task queued: the worker reconciliation loop will
        # retry enqueueing it without double-charging the user.
        raise HTTPException(503, "Task queue is temporarily unavailable") from exc
    return {"task_id": reservation.task_id, "status": "queued"}


@router.get("/task/{task_id}")
def task_status(task_id: str, authorization: str | None = Header(default=None), x_telegram_init_data: str | None = Header(default=None)):
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task.id,
        "status": task.status,
        "ci_status": task.ci_status,
        "ci_conclusion": task.ci_conclusion,
        "ci_run_id": task.ci_run_id,
        "ci_url": task.ci_url,
    }
