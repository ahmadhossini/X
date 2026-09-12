from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from api.github_connect import create_connect_state
from api.miniapp import _auth_user, _init_data
from core.config import settings

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


@router.get("/github/connect")
def github_connect(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict[str, str]:
    user = _auth_user(_init_data(authorization, x_telegram_init_data))
    if not settings.github_app_slug:
        raise HTTPException(status_code=503, detail="GitHub connection is unavailable")
    state = create_connect_state(user.telegram_id)
    return {
        "url": f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"
    }
