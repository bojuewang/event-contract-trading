from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from live_hedge_signals import build_signals, write_csv


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def signal_key(signal: dict[str, Any]) -> str:
    return "|".join([
        str(signal.get("event_id", "")),
        str(signal.get("first_leg_outcome", "")),
        str(signal.get("opposite_outcome", "")),
        str(signal.get("signal", "")),
    ])


def append_alerts(alert_path: Path, report: dict[str, Any], seen: set[str]) -> int:
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with alert_path.open("a", encoding="utf-8") as f:
        for signal in report.get("signals", []):
            if signal.get("signal") != "paper_trade_candidate":
                continue
            key = signal_key(signal)
            if key in seen:
                continue
            seen.add(key)
            event = {
                "alert_type": "paper_trade_candidate",
                "created_at": utc_now(),
                "event_id": signal.get("event_id"),
                "home_team": signal.get("home_team"),
                "away_team": signal.get("away_team"),
                "first_leg_outcome": signal.get("first_leg_outcome"),
                "opposite_outcome": signal.get("opposite_outcome"),
                "current_first_fair_prob": signal.get("current_first_fair_prob"),
                "current_opposite_fair_prob": signal.get("current_opposite_fair_prob"),
                "hit_probability": signal.get("hit_probability"),
                "expected_pnl_per_contract": signal.get("expected_pnl_per_contract"),
                "net_locked_profit_if_hit": signal.get("net_locked_profit_if_hit"),
                "reasons": signal.get("reasons"),
            }
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
    return count


def build_namespace(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        window_minutes=args.window_minutes,
        first_leg_price=args.first_leg_price,
        opposite_target_price=args.opposite_target_price,
        fee_per_contract=args.fee_per_contract,
        slippage_per_leg=args.slippage_per_leg,
        minutes_remaining=args.minutes_remaining,
        vol_per_sqrt_min=args.vol_per_sqrt_min,
        mean_reversion=args.mean_reversion,
        n_paths=args.n_paths,
        min_hit_probability=args.min_hit_probability,
        entry_tolerance=args.entry_tolerance,
        max_data_age_seconds=args.max_data_age_seconds,
        seed=args.seed,
    )


def run_once(args: argparse.Namespace, seen: set[str]) -> dict[str, Any]:
    params = build_namespace(args)
    report = build_signals(params)

    json_path = Path(args.json_out)
    csv_path = Path(args.csv_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, report["signals"])

    alert_count = append_alerts(Path(args.alerts_out), report, seen)
    summary = {
        "generated_at": report.get("generated_at"),
        "status": report.get("status"),
        "events_seen": report.get("events_seen"),
        "signals": len(report.get("signals", [])),
        "paper_trade_candidates": sum(1 for item in report.get("signals", []) if item.get("signal") == "paper_trade_candidate"),
        "new_alerts": alert_count,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously refresh live hedge signal reports and alert logs.")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--iterations", type=int, default=0, help="0 means run forever.")
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
    parser.add_argument("--alerts-out", default="data/alerts/hedge_signal_alerts.jsonl")
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    seen: set[str] = set()
    count = 0
    while True:
        run_once(args, seen)
        count += 1
        if args.iterations and count >= args.iterations:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
