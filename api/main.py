from __future__ import annotations

from fastapi import FastAPI

from database.session import init_db
from market.service import crypto_market

app = FastAPI(title="XAI MASTER API", version="3.0.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "XAI MASTER V3", "status": "online"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/market/crypto")
async def crypto_prices() -> list[dict]:
    return await crypto_market()
