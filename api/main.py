from __future__ import annotations

from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.github_connect import router as github_connect_router
from api.github_webhook import router as github_webhook_router
from api.miniapp import router as miniapp_router
from api.miniapp_billing import router as miniapp_billing_router
from api.miniapp_connect import router as miniapp_connect_router
from api.payments import router as payments_router
from code_agent.routes import router as code_agent_router
from core.config import settings
from database.session import init_db

app = FastAPI(title="XAI Code Agent API", version="1.2.0")


def _cors_origins() -> list[str]:
    origins: list[str] = []
    for value in (settings.miniapp_url, settings.public_base_url):
        parsed = urlparse(value)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        if origin and origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Telegram-Init-Data"],
)

app.include_router(code_agent_router)
app.include_router(github_connect_router)
app.include_router(github_webhook_router)
app.include_router(miniapp_router)
app.include_router(miniapp_billing_router)
app.include_router(miniapp_connect_router)
app.include_router(payments_router)
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
