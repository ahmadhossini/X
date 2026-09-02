from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Response
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


_PUBLIC_CONNECT_PAGE = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAI Code Agent — اتصال GitHub</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;background:radial-gradient(circle at top,#182338 0,#080b12 55%,#05070b 100%);color:#f5f7fb;font-family:system-ui,-apple-system,Segoe UI,Tahoma,sans-serif}.card{width:min(560px,100%);padding:38px;border:1px solid rgba(255,255,255,.13);border-radius:28px;background:rgba(255,255,255,.07);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);box-shadow:0 24px 80px rgba(0,0,0,.4);text-align:center}.brand{font-size:14px;letter-spacing:.12em;text-transform:uppercase;opacity:.65;margin-bottom:14px}.title{font-size:32px;font-weight:800;margin:0 0 14px}.text{font-size:16px;line-height:1.9;color:#c9d0dc;margin:0 auto 26px;max-width:470px}.steps{text-align:right;margin:0 0 28px;padding:18px 20px;border-radius:18px;background:rgba(0,0,0,.16);border:1px solid rgba(255,255,255,.08)}.steps div{margin:9px 0;color:#dce2ec}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#dce2ec;margin-left:9px}.button{display:inline-block;padding:14px 24px;border-radius:15px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.2);color:#fff;text-decoration:none;font-weight:700;transition:.2s}.button:hover{background:rgba(255,255,255,.2);transform:translateY(-1px)}.note{font-size:13px;color:#929baa;margin-top:18px;line-height:1.7}@media(max-width:480px){.card{padding:28px 20px}.title{font-size:27px}}
</style>
</head>
<body>
<main class="card">
<div class="brand">XAI CODE AGENT</div>
<h1 class="title">اتصال امن به GitHub</h1>
<p class="text">برای اتصال حساب GitHub خودت، ابتدا وارد ربات XAI Code Agent در تلگرام شو. اتصال برای حساب خودت انجام می‌شود و حساب GitHub کاربران دیگر به حساب تو متصل نخواهد شد.</p>
<section class="steps">
<div><span class="dot"></span>ورود به ربات XAI Code Agent</div>
<div><span class="dot"></span>انتخاب گزینه «اتصال GitHub»</div>
<div><span class="dot"></span>ورود به GitHub و انتخاب Repositoryهای موردنظر</div>
</section>
<a class="button" href="{telegram_url}">ورود به ربات و اتصال GitHub</a>
<p class="note">لینک اتصال مستقیم GitHub فقط پس از ایجاد نشست اختصاصی کاربر توسط ربات فعال می‌شود.</p>
</main>
</body>
</html>"""


def _public_connect_page() -> HTMLResponse:
    telegram_url = f"https://t.me/{settings.bot_username}?start=connect_github" if settings.bot_username else "#"
    html = _PUBLIC_CONNECT_PAGE.format(telegram_url=telegram_url)
    return HTMLResponse(html, status_code=200)


@router.get("/connect")
def connect(state: str | None = Query(default=None, min_length=20, max_length=128)) -> Response:
    # Public URL: show a landing page instead of exposing a state-validation error.
    # Stateful URL: continue the per-Telegram-user GitHub App installation flow.
    if not state:
        return _public_connect_page()

    with SessionLocal() as db:
        valid = db.scalar(select(GitHubConnectState.id).where(GitHubConnectState.state == state))
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid connection state")
    return RedirectResponse(_github_install_url(state), status_code=302)


@router.get("/setup", response_class=HTMLResponse, response_model=None)
async def setup(
    installation_id: int = Query(..., gt=0),
    state: str = Query(..., min_length=20, max_length=128),
    setup_action: str = Query(default="install"),
) -> Response:
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
