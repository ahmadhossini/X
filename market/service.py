from __future__ import annotations

from market.providers.coingecko import get_crypto_prices

DEFAULT_ASSETS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "TRX": "tron",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "TON": "the-open-network",
}


async def crypto_market() -> list[dict]:
    data = await get_crypto_prices(list(DEFAULT_ASSETS.values()))
    result = []
    for symbol, coin_id in DEFAULT_ASSETS.items():
        item = data.get(coin_id, {})
        result.append({
            "symbol": symbol,
            "price_usd": item.get("usd"),
            "change_24h": item.get("usd_24h_change", 0),
            "source": "coingecko",
        })
    return result
