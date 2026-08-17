from __future__ import annotations

import httpx


async def public_market() -> dict:
    result = {"gold_usd": None, "usd_irr": None, "sources": []}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get("https://api.metals.live/v1/spot/gold")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                result["gold_usd"] = data[0].get("gold")
                result["sources"].append("metals.live")
        except Exception:
            pass
        try:
            response = await client.get("https://api.frankfurter.app/latest", params={"from": "USD", "to": "EUR"})
            response.raise_for_status()
            data = response.json()
            result["usd_eur"] = data.get("rates", {}).get("EUR")
            result["sources"].append("frankfurter.app")
        except Exception:
            result["usd_eur"] = None
    return result
