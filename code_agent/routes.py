from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from code_agent.agent import AgentError, execute_task
from code_agent.github import GitHubRepoError
from code_agent.github_app import GitHubAppError, github_app_get
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
    if not expected or api_key != expected:
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
    try:
        return await execute_task(settings.gemini_api_key, settings.gemini_model, payload.repository, payload.request, payload.create_pr)
    except AgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubRepoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except GitHubAppError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/repositories")
async def repositories(x_api_key: str | None = Header(default=None)):
    _authorize(x_api_key)
    try:
        repos = await github_app_get("/installation/repositories?per_page=100")
        return {"repositories": repos.get("repositories", [])}
    except GitHubAppError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
