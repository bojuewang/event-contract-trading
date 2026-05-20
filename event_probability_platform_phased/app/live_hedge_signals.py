from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from config import get_settings
from odds_math import hedge_lock_profit, simulate_threshold_hit_probability


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: encode_value(value) for key, value in row._mapping.items()}


def latest_probability_rows(window_minutes: float) -> list[dict[str, Any]]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    query = text("""
        select
          event_id,
          outcome,
          count(*) as tick_count,
          avg(fair_prob)::float as avg_fair_prob,
          min(fair_prob)::float as min_fair_prob,
          max(fair_prob)::float as max_fair_prob,
          max(ingested_at) as latest_ingested_at,
          max(meta ->> 'home_team') as home_team,
          max(meta ->> 'away_team') as away_team,
          max(meta ->> 'commence_time') as commence_time
        from event_ticks
        where fair_prob is not null
          and ingested_at >= now() - (:window_minutes * interval '1 minute')
        group by event_id, outcome
        order by event_id, outcome
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"window_minutes": window_minutes}).fetchall()
    return [row_to_dict(row) for row in rows]


def normalize_event_probs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(row["avg_fair_prob"]) for row in rows if row.get("avg_fair_prob") is not None)
    if total <= 0:
        return rows
    normalized = []
    for row in rows:
        item = dict(row)
        item["current_fair_prob"] = float(item["avg_fair_prob"]) / total
        normalized.append(item)
    return normalized


def data_age_seconds(latest_ingested_at: str | None) -> float | None:
    if not latest_ingested_at:
        return None
    parsed = datetime.fromisoformat(latest_ingested_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def signal_label(
    expected_pnl: float,
    hit_probability: float,
    net_locked_profit: float,
    entry_edge: float,
    age_seconds: float | None,
    max_age_seconds: float,
    min_hit_probability: float,
    entry_tolerance: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if age_seconds is None or age_seconds > max_age_seconds:
        reasons.append("data_stale")
    if net_locked_profit <= 0:
        reasons.append("net_lock_not_positive")
    if hit_probability < min_hit_probability:
        reasons.append("target_hit_probability_low")
    if entry_edge < -entry_tolerance:
        reasons.append("first_leg_price_above_fair_value")
    if expected_pnl <= 0:
        reasons.append("expected_pnl_not_positive")

    if not reasons:
        return "paper_trade_candidate", ["passes_baseline_filters"]
    if reasons == ["target_hit_probability_low"]:
        return "watch", reasons
    return "reject", reasons


def build_signals(args: argparse.Namespace) -> dict[str, Any]:
    rows = latest_probability_rows(args.window_minutes)
    events: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        events.setdefault(str(row["event_id"]), []).append(row)

    hedge = hedge_lock_profit(args.first_leg_price, args.opposite_target_price, args.fee_per_contract)
    net_locked_profit = hedge.gross_locked_profit_per_contract - 2 * args.fee_per_contract - args.slippage_per_leg

    signals: list[dict[str, Any]] = []
    skipped_events: list[dict[str, Any]] = []

    for event_id, event_rows in sorted(events.items()):
        if len(event_rows) != 2:
            skipped_events.append({
                "event_id": event_id,
                "reason": "requires_exactly_two_outcomes",
                "outcome_count": len(event_rows),
            })
            continue

        normalized_rows = normalize_event_probs(event_rows)
        for first, opposite in (
            (normalized_rows[0], normalized_rows[1]),
            (normalized_rows[1], normalized_rows[0]),
        ):
            first_prob = float(first["current_fair_prob"])
            opposite_prob = float(opposite["current_fair_prob"])
            age = data_age_seconds(first.get("latest_ingested_at"))

            if opposite_prob <= args.opposite_target_price:
                threshold = {
                    "hit_probability": 1.0,
                    "expected_first_hit_minute": 0.0,
                    "paths": 0,
                    "dt_minutes": None,
                    "model": "already_at_or_below_target",
                }
            else:
                threshold = simulate_threshold_hit_probability(
                    current_prob=opposite_prob,
                    target_prob=args.opposite_target_price,
                    minutes_remaining=args.minutes_remaining,
                    vol_per_sqrt_min=args.vol_per_sqrt_min,
                    mean_reversion=args.mean_reversion,
                    n_paths=args.n_paths,
                    seed=args.seed,
                )

            hit_probability = float(threshold["hit_probability"])
            unhedged_win_profit = 1.0 - args.first_leg_price - args.fee_per_contract
            unhedged_loss_profit = -args.first_leg_price - args.fee_per_contract
            expected_unhedged_pnl_if_no_hit = (
                first_prob * unhedged_win_profit
                + (1.0 - first_prob) * unhedged_loss_profit
            )
            expected_pnl = (
                hit_probability * net_locked_profit
                + (1.0 - hit_probability) * expected_unhedged_pnl_if_no_hit
            )
            entry_edge = first_prob - args.first_leg_price
            target_gap = opposite_prob - args.opposite_target_price
            label, reasons = signal_label(
                expected_pnl=expected_pnl,
                hit_probability=hit_probability,
                net_locked_profit=net_locked_profit,
                entry_edge=entry_edge,
                age_seconds=age,
                max_age_seconds=args.max_data_age_seconds,
                min_hit_probability=args.min_hit_probability,
                entry_tolerance=args.entry_tolerance,
            )

            signals.append({
                "event_id": event_id,
                "home_team": first.get("home_team") or opposite.get("home_team"),
                "away_team": first.get("away_team") or opposite.get("away_team"),
                "commence_time": first.get("commence_time") or opposite.get("commence_time"),
                "first_leg_outcome": first["outcome"],
                "opposite_outcome": opposite["outcome"],
                "current_first_fair_prob": first_prob,
                "current_opposite_fair_prob": opposite_prob,
                "first_leg_price": args.first_leg_price,
                "opposite_target_price": args.opposite_target_price,
                "entry_edge": entry_edge,
                "opposite_target_gap": target_gap,
                "hit_probability": hit_probability,
                "expected_first_hit_minute": threshold.get("expected_first_hit_minute"),
                "gross_locked_profit_if_hit": hedge.gross_locked_profit_per_contract,
                "net_locked_profit_if_hit": net_locked_profit,
                "expected_unhedged_pnl_if_no_hit": expected_unhedged_pnl_if_no_hit,
                "expected_pnl_per_contract": expected_pnl,
                "roi_on_cost_if_hit": hedge.roi_on_cost,
                "tick_count_first": int(first["tick_count"]),
                "tick_count_opposite": int(opposite["tick_count"]),
                "latest_ingested_at": first.get("latest_ingested_at"),
                "latest_age_seconds": age,
                "signal": label,
                "reasons": reasons,
            })

    signals.sort(key=lambda item: (item["signal"] != "paper_trade_candidate", -item["expected_pnl_per_contract"]))
    return {
        "status": "ok" if signals else "no_binary_signals",
        "generated_at": utc_now(),
        "parameters": {
            "window_minutes": args.window_minutes,
            "first_leg_price": args.first_leg_price,
            "opposite_target_price": args.opposite_target_price,
            "fee_per_contract": args.fee_per_contract,
            "slippage_per_leg": args.slippage_per_leg,
            "minutes_remaining": args.minutes_remaining,
            "vol_per_sqrt_min": args.vol_per_sqrt_min,
            "mean_reversion": args.mean_reversion,
            "n_paths": args.n_paths,
            "min_hit_probability": args.min_hit_probability,
            "entry_tolerance": args.entry_tolerance,
            "max_data_age_seconds": args.max_data_age_seconds,
        },
        "hedge_lock_profit": asdict(hedge),
        "events_seen": len(events),
        "signals": signals,
        "skipped_events": skipped_events,
    }


def write_csv(path: Path, signals: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not signals:
        path.write_text("", encoding="utf-8")
        return
    fields = [
        "event_id",
        "home_team",
        "away_team",
        "first_leg_outcome",
        "opposite_outcome",
        "current_first_fair_prob",
        "current_opposite_fair_prob",
        "entry_edge",
        "opposite_target_gap",
        "hit_probability",
        "expected_pnl_per_contract",
        "net_locked_profit_if_hit",
        "signal",
        "reasons",
        "latest_age_seconds",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for signal in signals:
            row = {field: signal.get(field) for field in fields}
            row["reasons"] = "|".join(signal.get("reasons", []))
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate live hedge signal snapshots from event_ticks.")
    parser.add_argument("--window-minutes", type=float, default=3.0)
    parser.add_argument("--first-leg-price", type=float, default=0.40)
    parser.add_argument("--opposite-target-price", type=float, default=0.40)
    parser.add_argument("--fee-per-contract", type=float, default=0.0)
    parser.add_argument("--slippage-per-leg", type=float, default=0.005)
    parser.add_argument("--minutes-remaining", type=float, default=36.0)
    parser.add_argument("--vol-per-sqrt-min", type=float, default=0.045)
    parser.add_argument("--mean-reversion", type=float, default=0.05)
    parser.add_argument("--n-paths", type=int, default=20000)
    parser.add_argument("--min-hit-probability", type=float, default=0.15)
    parser.add_argument("--entry-tolerance", type=float, default=0.03)
    parser.add_argument("--max-data-age-seconds", type=float, default=30.0)
    parser.add_argument("--json-out", default="data/reports/live_hedge_signals.json")
    parser.add_argument("--csv-out", default="data/reports/live_hedge_signals.csv")
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    report = build_signals(args)
    json_path = Path(args.json_out)
    csv_path = Path(args.csv_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, report["signals"])

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved {json_path}")
    print(f"saved {csv_path}")


if __name__ == "__main__":
    main()
