from __future__ import annotations
import json, os
import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from backend.miniapp_auth import validate_telegram_init_data
from backend.chat_registry import registry
from backend.chat_stats import stats
from bot.services.group_settings_store import store

router=APIRouter(prefix="/api/miniapp",tags=["miniapp"])

def _identity(init_data:str)->dict:
    try:
        pairs=validate_telegram_init_data(init_data,os.environ["BOT_TOKEN"]);user=json.loads(pairs.get("user","{}"))
        if not user.get("id"):raise ValueError("Telegram user missing")
        return user
    except (KeyError,ValueError,json.JSONDecodeError) as exc:raise HTTPException(status_code=401,detail="Invalid Telegram session") from exc

async def _telegram(method:str,**params):
    token=os.environ.get("BOT_TOKEN","")
    async with httpx.AsyncClient(timeout=8) as client:
        r=await client.get(f"https://api.telegram.org/bot{token}/{method}",params=params);r.raise_for_status();data=r.json()
        if not data.get("ok"):raise HTTPException(status_code=502,detail="Telegram API error")
        return data["result"]

async def _admin(user_id:int,chat_id:int)->bool:
    try:return (await _telegram("getChatMember",chat_id=chat_id,user_id=user_id)).get("status") in {"creator","administrator"}
    except Exception:return False

@router.get("/me")
def me(x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data);return {"id":user["id"],"first_name":user.get("first_name",""),"last_name":user.get("last_name"),"username":user.get("username"),"photo_url":user.get("photo_url"),"language_code":user.get("language_code")}

@router.get("/groups")
async def groups(x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data);out=[]
    for chat in registry.all():
        if await _admin(user["id"],chat.chat_id):
            try:info=await _telegram("getChat",chat_id=chat.chat_id)
            except Exception:info={}
            s=stats.get(chat.chat_id)
            out.append({"chat_id":chat.chat_id,"title":chat.title,"type":chat.chat_type,"username":chat.username,"member_count":info.get("members_count"),"message_count":s["messages"],"deleted_count":s["deleted"]})
    return {"groups":out}

@router.get("/groups/{chat_id}")
async def group(chat_id:int,x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data)
    if not await _admin(user["id"],chat_id):raise HTTPException(status_code=403,detail="You are not an administrator of this chat")
    record=next((c for c in registry.all() if c.chat_id==chat_id),None)
    if not record:raise HTTPException(status_code=404,detail="Chat not found")
    try:info=await _telegram("getChat",chat_id=chat_id)
    except Exception:info={}
    return {"chat_id":chat_id,"title":record.title,"type":record.chat_type,"username":record.username,"member_count":info.get("members_count"),"stats":stats.get(chat_id),"telegram":info}

@router.get("/groups/{chat_id}/stats")
async def group_stats(chat_id:int,x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data)
    if not await _admin(user["id"],chat_id):raise HTTPException(status_code=403,detail="Forbidden")
    return stats.get(chat_id)

class SettingChange(BaseModel):
    feature:str
    enabled:bool

@router.get("/groups/{chat_id}/settings")
async def group_settings(chat_id:int,x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data)
    if not await _admin(user["id"],chat_id):raise HTTPException(status_code=403,detail="Forbidden")
    from dataclasses import asdict
    return asdict(store.get(chat_id))

@router.patch("/groups/{chat_id}/settings")
async def update_group_setting(chat_id:int,change:SettingChange,x_telegram_init_data:str=Header(default="")):
    user=_identity(x_telegram_init_data)
    if not await _admin(user["id"],chat_id):raise HTTPException(status_code=403,detail="Forbidden")
    try:
        from dataclasses import asdict
        return asdict(store.set(chat_id,change.feature,change.enabled))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
