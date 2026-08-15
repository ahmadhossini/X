from __future__ import annotations

import os

import httpx


class TelegramAPIError(RuntimeError):
    pass


class TelegramAPI:
    def __init__(self) -> None:
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise TelegramAPIError("BOT_TOKEN is not configured")
        self.base = f"https://api.telegram.org/bot{token}"

    async def get_chat_member(self, chat_id: int, user_id: int) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{self.base}/getChatMember", json={"chat_id": chat_id, "user_id": user_id})
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("description", "Telegram API error"))
        return payload["result"]

    async def get_chat(self, chat_id: int) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{self.base}/getChat", json={"chat_id": chat_id})
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("description", "Telegram API error"))
        return payload["result"]
