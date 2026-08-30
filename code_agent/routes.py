from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.github_app import GitHubAppError, github_app_get
from code_agent.service import CodeAgentError, analyze_code
from core.config import settings

router = APIRouter(prefix="/api/code-agent", tags=["code-agent"])

class AnalyzeRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200_000)

@router.get("/health")
def code_agent_health() -> dict[str, str]:
    return {"status":"ok","service":"xai-code-agent"}

@router.post("/analyze")
async def analyze(payload: AnalyzeRequest):
    try:
        return await analyze_code(settings.gemini_api_key, settings.gemini_model, payload.filename, payload.content)
    except CodeAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.get("/repositories")
async def repositories():
    try:
        repos = await github_app_get("/installation/repositories?per_page=100")
        return {"repositories": repos.get("repositories", [])}
    except GitHubAppError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
