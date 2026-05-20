from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from clients.the_odds_api import TheOddsAPIClient
from config import get_settings
from ingest_odds import transform_odds_response


def _safe_ts(ts: str) -> str:
    return ts.replace(":", "").replace("-", "").replace(".", "").replace("Z", "Z")


def _events_from_historical_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("events"), list):
            return payload["events"]
    return []


async def fetch_one(client: TheOddsAPIClient, snapshot_iso: str, out_dir: Path) -> dict[str, Any]:
    settings = get_settings()
    payload = await client.get_historical_odds(
        snapshot_iso=snapshot_iso,
        sport=settings.odds_api_sport,
        regions=settings.odds_api_regions,
        markets=settings.odds_api_markets,
        odds_format=settings.odds_api_odds_format,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"historical_odds_{_safe_ts(snapshot_iso)}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    events = _events_from_historical_payload(payload)
    rows = transform_odds_response(events, settings.odds_api_odds_format)
    for row in rows:
        row["snapshot_iso"] = snapshot_iso
    rows_path = out_dir / f"historical_rows_{_safe_ts(snapshot_iso)}.csv"
    pd.DataFrame(rows).to_csv(rows_path, index=False)
    return {"snapshot_iso": snapshot_iso, "raw_path": str(raw_path), "rows_path": str(rows_path), "events": len(events), "rows": len(rows)}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical odds snapshots from The Odds API.")
    parser.add_argument("--snapshots", required=True, help="Comma-separated ISO timestamps, e.g. 2026-05-19T20:00:00Z,2026-05-19T21:00:00Z")
    parser.add_argument("--out-dir", default="data/historical_odds")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.odds_api_key or settings.odds_api_key in {"replace_me", "你的_the_odds_api_key"}:
        raise RuntimeError("ODDS_API_KEY is required for historical API fetch")

    snapshots = [s.strip() for s in args.snapshots.split(",") if s.strip()]
    if not snapshots:
        raise RuntimeError("No snapshots provided")

    client = TheOddsAPIClient(api_key=settings.odds_api_key)
    out_dir = Path(args.out_dir)
    results = []
    for ts in snapshots:
        print(f"[historical] fetching {ts}")
        result = await fetch_one(client, ts, out_dir)
        print(f"[historical] {result}")
        results.append(result)

    summary = {"fetched_at": datetime.now(timezone.utc).isoformat(), "results": results}
    summary_path = out_dir / "historical_fetch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[historical] summary saved: {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
