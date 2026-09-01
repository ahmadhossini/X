from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from code_agent.github_app import GitHubAppError, github_app_get_installation
from core.config import settings
from database.models import GitHubConnectState, GitHubInstallation, User
from database.session import SessionLocal

router = APIRouter(prefix="/github", tags=["github-connect"])
STATE_TTL_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < _now()


def create_connect_state(telegram_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.add(
            GitHubConnectState(
                state=token,
                telegram_id=telegram_id,
                expires_at=_now() + timedelta(minutes=STATE_TTL_MINUTES),
            )
        )
        db.commit()
    return token


def _github_install_url(state: str) -> str:
    if not settings.github_app_slug:
        raise HTTPException(status_code=500, detail="GITHUB_APP_SLUG is not configured")
    params = urlencode({"state": state})
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new?{params}"


@router.get("/connect")
def connect(state: str = Query(..., min_length=20, max_length=128)) -> RedirectResponse:
    with SessionLocal() as db:
        valid = db.scalar(select(GitHubConnectState.id).where(GitHubConnectState.state == state))
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid connection state")
    return RedirectResponse(_github_install_url(state), status_code=302)


@router.get("/setup", response_class=HTMLResponse)
async def setup(
    installation_id: int = Query(..., gt=0),
    state: str = Query(..., min_length=20, max_length=128),
    setup_action: str = Query(default="install"),
) -> HTMLResponse | RedirectResponse:
    with SessionLocal() as db:
        connect_state = db.scalar(select(GitHubConnectState).where(GitHubConnectState.state == state))
        if not connect_state or connect_state.used_at is not None or _is_expired(connect_state.expires_at):
            return HTMLResponse("GitHub connection state is invalid or expired.", status_code=400)

        connect_state.used_at = _now()
        if setup_action == "uninstall":
            db.query(GitHubInstallation).filter(GitHubInstallation.installation_id == installation_id).update({"active": False})
            db.commit()
            return HTMLResponse("GitHub connection was removed.", status_code=200)

        try:
            installation = await github_app_get_installation(installation_id)
        except GitHubAppError:
            db.rollback()
            return HTMLResponse("GitHub connection could not be verified.", status_code=502)

        account = installation.get("account") or {}
        github_user_id = account.get("id")
        github_login = account.get("login") or account.get("name") or "GitHub user"

        user = db.scalar(select(User).where(User.telegram_id == connect_state.telegram_id))
        if not user:
            user = User(telegram_id=connect_state.telegram_id, github_login=github_login)
            db.add(user)
            db.flush()
        else:
            user.github_login = github_login

        existing = db.scalar(select(GitHubInstallation).where(GitHubInstallation.installation_id == installation_id))
        if existing:
            existing.user_id = user.id
            existing.github_user_id = github_user_id
            existing.github_login = github_login
            existing.active = True
        else:
            db.add(
                GitHubInstallation(
                    user_id=user.id,
                    installation_id=installation_id,
                    github_user_id=github_user_id,
                    github_login=github_login,
                    active=True,
                )
            )
        db.commit()

    if settings.bot_username:
        return RedirectResponse(f"https://t.me/{settings.bot_username}?start=github_connected", status_code=302)
    return HTMLResponse("GitHub connected successfully. Return to Telegram.", status_code=200)
