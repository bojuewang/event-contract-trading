from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select

from clients.the_odds_api import TheOddsAPIClient
from config import get_settings
from ingest_odds import transform_odds_response
from storage import event_ticks, make_engine, write_ticks


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def count_ticks(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(select(func.count()).select_from(event_ticks))
        return int(result.scalar_one())


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot real data ingestion probe for The Odds API.")
    parser.add_argument("--report", default="data/reports/real_data_ingestion_report.json")
    parser.add_argument("--preview-rows", type=int, default=8)
    args = parser.parse_args()

    settings = get_settings()
    report_path = Path(args.report)

    if not settings.odds_api_key or settings.odds_api_key in {"replace_me", "你的_the_odds_api_key"}:
        report = {
            "status": "blocked_missing_odds_api_key",
            "generated_at": utc_now(),
            "required_env": "ODDS_API_KEY",
            "next_step": "Edit .env and set ODDS_API_KEY to a real The Odds API key, then rerun Phase 11.",
        }
        write_report(report_path, report)
        raise SystemExit("ODDS_API_KEY is not configured. Wrote missing-key report.")

    client = TheOddsAPIClient(api_key=settings.odds_api_key)
    engine = make_engine(settings.database_url)

    report: dict[str, Any] = {
        "status": "started",
        "generated_at": utc_now(),
        "sport": settings.odds_api_sport,
        "regions": settings.odds_api_regions,
        "markets": settings.odds_api_markets,
        "odds_format": settings.odds_api_odds_format,
    }

    try:
        before = await count_ticks(engine)
        events = await client.get_odds(
            sport=settings.odds_api_sport,
            regions=settings.odds_api_regions,
            markets=settings.odds_api_markets,
            odds_format=settings.odds_api_odds_format,
        )
        rows = transform_odds_response(events, settings.odds_api_odds_format)
        written = await write_ticks(engine, rows)
        after = await count_ticks(engine)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        body = exc.response.text[:500]
        report.update({
            "status": "failed_http_error",
            "http_status": status_code,
            "response_preview": body,
            "finished_at": utc_now(),
        })
        write_report(report_path, report)
        raise SystemExit(f"The Odds API returned HTTP {status_code}. Wrote report to {report_path}") from exc
    except Exception as exc:
        report.update({
            "status": "failed_exception",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "finished_at": utc_now(),
        })
        write_report(report_path, report)
        raise
    finally:
        await engine.dispose()

    sources = sorted({row["source"] for row in rows})
    markets = sorted({row["market"] for row in rows})
    event_ids = sorted({row["event_id"] for row in rows if row.get("event_id")})

    status = "ok"
    if not events:
        status = "ok_no_events_returned"
    elif not rows:
        status = "ok_no_rows_transformed"

    report.update({
        "status": status,
        "finished_at": utc_now(),
        "events_received": len(events),
        "rows_transformed": len(rows),
        "rows_written": written,
        "event_ticks_before": before,
        "event_ticks_after": after,
        "unique_events": len(event_ids),
        "sources": sources[:25],
        "markets_seen": markets,
        "preview": rows[: args.preview_rows],
    })
    write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
