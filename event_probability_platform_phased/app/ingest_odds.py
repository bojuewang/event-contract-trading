from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from config import get_settings
from clients.the_odds_api import TheOddsAPIClient
from odds_math import decimal_to_probability, american_to_probability, normalize_remove_vig
from storage import make_engine, write_ticks


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _price_to_raw_prob(price: float, odds_format: str) -> float:
    if odds_format == "american":
        return american_to_probability(price)
    return decimal_to_probability(price)


def transform_odds_response(events: list[dict[str, Any]], odds_format: str = "decimal") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for event in events:
        event_id = event.get("id")
        bookmakers = event.get("bookmakers", [])
        for bookmaker in bookmakers:
            book_key = bookmaker.get("key")
            source_ts = bookmaker.get("last_update")
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "h2h")
                outcomes = market.get("outcomes", [])
                raw_probs = []
                for outcome in outcomes:
                    try:
                        raw_probs.append(_price_to_raw_prob(float(outcome["price"]), odds_format))
                    except Exception:
                        raw_probs.append(float("nan"))
                clean_raw = [p for p in raw_probs if p == p]
                fair_probs = normalize_remove_vig(clean_raw) if clean_raw else []
                fair_idx = 0
                for idx, outcome in enumerate(outcomes):
                    raw_prob = raw_probs[idx]
                    fair_prob = None
                    if raw_prob == raw_prob and fair_idx < len(fair_probs):
                        fair_prob = fair_probs[fair_idx]
                        fair_idx += 1
                    rows.append({
                        "source": f"the_odds_api:{book_key}",
                        "event_id": event_id,
                        "market": market_key,
                        "outcome": outcome.get("name", "unknown"),
                        "source_ts": _parse_iso_datetime(source_ts),
                        "price": outcome.get("price"),
                        "raw_prob": raw_prob if raw_prob == raw_prob else None,
                        "fair_prob": fair_prob,
                        "meta": {
                            "home_team": event.get("home_team"),
                            "away_team": event.get("away_team"),
                            "commence_time": event.get("commence_time"),
                            "bookmaker": bookmaker.get("title"),
                            "ingest_ts": now.isoformat(),
                        },
                    })
    return rows


async def main() -> None:
    settings = get_settings()
    if not settings.odds_api_key or settings.odds_api_key == "replace_me":
        raise RuntimeError("Please set ODDS_API_KEY in .env")

    client = TheOddsAPIClient(api_key=settings.odds_api_key)
    engine = make_engine(settings.database_url)

    while True:
        try:
            events = await client.get_odds(
                sport=settings.odds_api_sport,
                regions=settings.odds_api_regions,
                markets=settings.odds_api_markets,
                odds_format=settings.odds_api_odds_format,
            )
            rows = transform_odds_response(events, settings.odds_api_odds_format)
            n = await write_ticks(engine, rows)
            print(f"[{datetime.now(timezone.utc).isoformat()}] wrote {n} rows")
        except Exception as exc:
            print(f"ingest error: {exc}")
        await asyncio.sleep(settings.odds_api_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
