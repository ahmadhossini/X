from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from code_agent.service import CodeAgentError, analyze_code
from core.config import settings

router = APIRouter(prefix="/api/code-agent", tags=["code-agent"])


class AnalyzeRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200_000)


class TaskRequest(BaseModel):
    repository: str = Field(pattern=r"^[^/ ]+/[^/ ]+$")
    request: str = Field(min_length=3, max_length=4000)
    create_pr: bool = True


def _authorize(api_key: str | None) -> None:
    expected = settings.code_agent_api_key
    supplied = api_key or ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health")
def code_agent_health() -> dict[str, str]:
    return {"status": "ok", "service": "xai-code-agent"}


@router.post("/analyze")
async def analyze(payload: AnalyzeRequest, x_api_key: str | None = Header(default=None)):
    _authorize(x_api_key)
    try:
        return await analyze_code(settings.gemini_api_key, settings.gemini_model, payload.filename, payload.content)
    except CodeAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/task")
async def task(payload: TaskRequest, x_api_key: str | None = Header(default=None)):
    _authorize(x_api_key)
    raise HTTPException(status_code=400, detail="Use the Telegram bot for user-scoped GitHub tasks.")


@router.get("/repositories")
async def repositories(x_api_key: str | None = Header(default=None)):
    _authorize(x_api_key)
    raise HTTPException(status_code=400, detail="Use the Telegram bot for user-scoped GitHub repositories.")
