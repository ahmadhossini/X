from __future__ import annotations

import httpx


async def public_market() -> dict:
    result = {"gold_usd": None, "gold_irr": None, "usd_irr": None, "eur_irr": None, "usd_eur": None, "sources": [], "freshness": "unavailable"}

    # Reference market feed. Keep this call server-side so the Mini App never
    # needs to expose a provider key and can later be replaced by a paid feed.
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get("https://persiantoolbox.ir/api/market")
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            currencies = data.get("currencies", {}) if isinstance(data, dict) else {}
            gold = data.get("gold", {}) if isinstance(data, dict) else {}
            if isinstance(currencies, dict):
                usd = currencies.get("USD", {})
                irr = currencies.get("IRR", {})
                eur = currencies.get("EUR", {})
                if isinstance(usd, dict) and usd.get("rate") is not None:
                    result["usd_irr"] = usd.get("rate")
                if isinstance(eur, dict) and eur.get("rate") is not None:
                    result["eur_irr"] = eur.get("rate")
                if isinstance(irr, dict) and irr.get("rate") is not None and result["usd_irr"] is None:
                    result["usd_irr"] = irr.get("rate")
            if isinstance(gold, dict) and gold.get("pricePerGram") is not None:
                result["gold_irr"] = gold.get("pricePerGram")
            result["freshness"] = data.get("freshness", "unknown")
            result["sources"].append("persiantoolbox")
    except Exception:
        pass

    # Keep the existing global gold feed as a fallback for deployments where
    # the Iran market feed is unavailable.
    if result["gold_usd"] is None:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get("https://api.metals.live/v1/spot/gold")
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    result["gold_usd"] = data[0].get("gold")
                    result["sources"].append("metals.live")
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get("https://api.frankfurter.app/latest", params={"from": "USD", "to": "EUR"})
            response.raise_for_status()
            data = response.json()
            result["usd_eur"] = data.get("rates", {}).get("EUR")
            result["sources"].append("frankfurter.app")
    except Exception:
        pass

    return result
