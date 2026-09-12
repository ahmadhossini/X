from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.github_connect import router as github_connect_router
from api.github_webhook import router as github_webhook_router
from api.miniapp import router as miniapp_router
from api.miniapp_connect import router as miniapp_connect_router
from code_agent.routes import router as code_agent_router
from database.session import init_db

app = FastAPI(title="XAI Code Agent API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(code_agent_router)
app.include_router(github_connect_router)
app.include_router(github_webhook_router)
app.include_router(miniapp_router)
app.include_router(miniapp_connect_router)
app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "XAI Code Agent", "status": "online"}


@app.get("/miniapp")
def miniapp() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/", status_code=307)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "code_agent": "embedded", "github": "enabled"}
