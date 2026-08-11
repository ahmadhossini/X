from __future__ import annotations

import httpx

BASE_URL = "https://api.coingecko.com/api/v3"


async def get_crypto_prices(ids: list[str]) -> dict:
    params = {
        "ids": ",".join(ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{BASE_URL}/simple/price", params=params)
        response.raise_for_status()
        return response.json()
