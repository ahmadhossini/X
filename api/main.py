from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.miniapp_api import router as miniapp_router
from backend.miniapp_groups import router as groups_router
from database.session import init_db
from market.service import crypto_market
from market.providers.public_markets import public_market
from market.providers.coingecko import get_crypto_history
BASE_DIR=Path(__file__).resolve().parent.parent; MINIAPP_DIR=BASE_DIR/"miniapp"
app=FastAPI(title="XAI MASTER API",version="3.0.0"); app.include_router(miniapp_router); app.include_router(groups_router)
if MINIAPP_DIR.exists(): app.mount("/miniapp",StaticFiles(directory=MINIAPP_DIR,html=True),name="miniapp")
@app.on_event("startup")
def startup()->None: init_db()
@app.get("/")
def root()->dict[str,str]: return {"name":"XAI MASTER V3","status":"online","miniapp":"/miniapp/"}
@app.get("/health")
def health()->dict[str,str]: return {"status":"ok","version":"3.0.0"}
@app.get("/miniapp")
def miniapp_redirect()->FileResponse: return FileResponse(MINIAPP_DIR/"index.html")
@app.get("/api/market/crypto")
async def crypto_prices()->list[dict]: return await crypto_market()
@app.get("/api/market/crypto/{coin_id}/history")
async def crypto_history(coin_id:str)->dict:
    allowed={"bitcoin","ethereum","tether","tron","binancecoin","solana","ripple","dogecoin","the-open-network"}
    if coin_id not in allowed: raise HTTPException(400,"Unsupported asset")
    return {"coin_id":coin_id,"prices":await get_crypto_history(coin_id)}
@app.get("/api/market/public")
async def public_prices()->dict: return await public_market()
