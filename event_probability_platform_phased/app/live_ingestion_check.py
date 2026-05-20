from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from config import get_settings


def encode_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: encode_value(value) for key, value in row._mapping.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize live ingestion worker output.")
    parser.add_argument("--report", default="data/reports/live_ingestion_worker_report.json")
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        total = conn.execute(text("select count(*) from event_ticks")).scalar_one()
        latest_ingested_at = conn.execute(text("select max(ingested_at) from event_ticks")).scalar_one()
        unique_events = conn.execute(text("select count(distinct event_id) from event_ticks")).scalar_one()
        unique_sources = conn.execute(text("select count(distinct source) from event_ticks")).scalar_one()

        latest_rows = conn.execute(text("""
            select source, event_id, market, outcome, source_ts, ingested_at, price, raw_prob, fair_prob, meta
            from event_ticks
            order by ingested_at desc, id desc
            limit :limit
        """), {"limit": args.limit}).fetchall()

        snapshot_rows = conn.execute(text("""
            with recent as (
              select *
              from event_ticks
              where ingested_at >= now() - interval '3 minutes'
            )
            select
              event_id,
              outcome,
              count(*) as tick_count,
              round(avg(fair_prob)::numeric, 6) as avg_fair_prob,
              round(min(fair_prob)::numeric, 6) as min_fair_prob,
              round(max(fair_prob)::numeric, 6) as max_fair_prob,
              max(ingested_at) as latest_ingested_at
            from recent
            where fair_prob is not null
            group by event_id, outcome
            order by event_id, outcome
        """)).fetchall()

    now = datetime.now(timezone.utc)
    latest_age_seconds = None
    if latest_ingested_at is not None:
        if latest_ingested_at.tzinfo is None:
            latest_ingested_at = latest_ingested_at.replace(tzinfo=timezone.utc)
        latest_age_seconds = (now - latest_ingested_at).total_seconds()

    report = {
        "status": "ok" if total > 0 else "no_ticks",
        "generated_at": utc_now(),
        "total_event_ticks": int(total),
        "unique_events": int(unique_events),
        "unique_sources": int(unique_sources),
        "latest_ingested_at": encode_value(latest_ingested_at),
        "latest_age_seconds": latest_age_seconds,
        "recent_probability_snapshot": [row_to_dict(row) for row in snapshot_rows],
        "latest_rows": [row_to_dict(row) for row in latest_rows],
    }

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
