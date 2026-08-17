from __future__ import annotations
import httpx
BASE_URL = "https://api.coingecko.com/api/v3"
async def get_crypto_prices(ids: list[str]) -> dict:
    params={"ids":",".join(ids),"vs_currencies":"usd","include_24hr_change":"true"}
    async with httpx.AsyncClient(timeout=10) as client:
        response=await client.get(f"{BASE_URL}/simple/price",params=params); response.raise_for_status(); return response.json()
async def get_crypto_history(coin_id: str, days: int = 7) -> list[float]:
    async with httpx.AsyncClient(timeout=10) as client:
        response=await client.get(f"{BASE_URL}/coins/{coin_id}/market_chart",params={"vs_currency":"usd","days":days,"interval":"hourly"}); response.raise_for_status()
        return [float(point[1]) for point in response.json().get("prices", [])]
