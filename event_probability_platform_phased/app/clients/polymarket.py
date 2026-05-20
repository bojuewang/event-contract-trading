from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class PolymarketClient:
    gamma_base: str = "https://gamma-api.polymarket.com"
    clob_base: str = "https://clob.polymarket.com"
    timeout: float = 10.0

    async def search_events(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        params = {"q": query, "limit": limit}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.gamma_base}/events", params=params)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("events", [])

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.clob_base}/book", params={"token_id": token_id})
            r.raise_for_status()
            return r.json()
