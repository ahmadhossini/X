from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database.session import init_db
from market.service import crypto_market

BASE_DIR = Path(__file__).resolve().parent.parent
MINIAPP_DIR = BASE_DIR / "miniapp"

app = FastAPI(title="XAI MASTER API", version="3.0.0")

if MINIAPP_DIR.exists():
    app.mount("/miniapp", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "XAI MASTER V3", "status": "online", "miniapp": "/miniapp/"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "3.0.0"}


@app.get("/miniapp")
def miniapp_redirect() -> FileResponse:
    return FileResponse(MINIAPP_DIR / "index.html")


@app.get("/api/market/crypto")
async def crypto_prices() -> list[dict]:
    return await crypto_market()
