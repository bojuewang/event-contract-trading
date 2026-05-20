from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class TheOddsAPIClient:
    api_key: str
    base_url: str = "https://api.the-odds-api.com"
    timeout: float = 10.0

    async def get_sports(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/v4/sports", params={"apiKey": self.api_key})
            r.raise_for_status()
            return r.json()

    async def get_odds(
        self,
        sport: str = "basketball_nba",
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "decimal",
    ) -> list[dict[str, Any]]:
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/v4/sports/{sport}/odds", params=params)
            r.raise_for_status()
            return r.json()

    async def get_historical_odds(
        self,
        snapshot_iso: str,
        sport: str = "basketball_nba",
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "decimal",
    ) -> dict[str, Any]:
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
            "date": snapshot_iso,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/v4/historical/sports/{sport}/odds", params=params)
            r.raise_for_status()
            return r.json()
