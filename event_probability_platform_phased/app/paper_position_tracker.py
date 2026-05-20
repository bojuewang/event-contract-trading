from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_signal(
    signals: list[dict[str, Any]],
    event_id: str | None,
    first_leg_outcome: str,
    opposite_outcome: str,
) -> dict[str, Any] | None:
    for signal in signals:
        if event_id and signal.get("event_id") != event_id:
            continue
        if (
            signal.get("first_leg_outcome") == first_leg_outcome
            and signal.get("opposite_outcome") == opposite_outcome
        ):
            return signal
    if event_id:
        return None
    for signal in signals:
        if (
            signal.get("first_leg_outcome") == first_leg_outcome
            and signal.get("opposite_outcome") == opposite_outcome
        ):
            return signal
    return None


def bootstrap_positions(path: Path, live_signals: dict[str, Any]) -> dict[str, Any]:
    signals = live_signals.get("signals", [])
    cavs_signal = find_signal(
        signals=signals,
        event_id=None,
        first_leg_outcome="Cleveland Cavaliers",
        opposite_outcome="New York Knicks",
    )
    positions: list[dict[str, Any]] = []
    if cavs_signal:
        positions.append({
            "position_id": "paper_cavaliers_040_to_knicks_040",
            "status": "open",
            "paper_only": True,
            "created_at": utc_now(),
            "created_from": "phase_17_bootstrap_user_example",
            "event_id": cavs_signal.get("event_id"),
            "home_team": cavs_signal.get("home_team"),
            "away_team": cavs_signal.get("away_team"),
            "first_leg_outcome": "Cleveland Cavaliers",
            "first_leg_price": 0.40,
            "opposite_outcome": "New York Knicks",
            "opposite_target_price": 0.40,
            "quantity": 1.0,
            "fee_per_contract": 0.0,
            "slippage_per_leg": 0.005,
            "notes": "Paper-only tracker for the original 40/40 Cavaliers -> Knicks example.",
        })
    config = {
        "paper_only": True,
        "created_at": utc_now(),
        "description": "Paper positions tracked against live fair probabilities. This file never places real orders.",
        "positions": positions,
    }
    save_json(path, config)
    return config


def action_for_position(
    position: dict[str, Any],
    signal: dict[str, Any],
    risk_status: str,
    min_high_hit_probability: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if risk_status != "ok":
        return "blocked_by_risk", [f"risk_status_{risk_status}"]

    current_opposite = float(signal["current_opposite_fair_prob"])
    target = float(position["opposite_target_price"])
    hit_probability = float(signal.get("hit_probability") or 0.0)
    latest_age = signal.get("latest_age_seconds")

    if latest_age is not None and float(latest_age) > 30:
        return "blocked_stale_signal", ["signal_stale"]
    if current_opposite <= target:
        return "paper_second_leg_ready", ["opposite_at_or_below_target"]
    if hit_probability >= min_high_hit_probability:
        return "watch_high_hit_probability", ["target_not_hit_yet", "hit_probability_high"]
    return "wait", ["target_not_hit_yet"]


def evaluate_positions(
    config: dict[str, Any],
    live_signals: dict[str, Any],
    risk: dict[str, Any],
    min_high_hit_probability: float,
) -> dict[str, Any]:
    signals = live_signals.get("signals", [])
    risk_status = risk.get("status", "missing")
    rows: list[dict[str, Any]] = []

    for position in config.get("positions", []):
        if position.get("status") != "open":
            continue
        match = find_signal(
            signals=signals,
            event_id=position.get("event_id"),
            first_leg_outcome=position["first_leg_outcome"],
            opposite_outcome=position["opposite_outcome"],
        )
        if not match:
            rows.append({
                "position_id": position.get("position_id"),
                "status": "unmatched",
                "action": "no_matching_live_signal",
                "reasons": ["live_signal_missing"],
                "position": position,
            })
            continue

        quantity = float(position.get("quantity", 1.0))
        first_price = float(position["first_leg_price"])
        opposite_target = float(position["opposite_target_price"])
        fee = float(position.get("fee_per_contract", 0.0))
        slippage = float(position.get("slippage_per_leg", 0.0))
        current_first = float(match["current_first_fair_prob"])
        current_opposite = float(match["current_opposite_fair_prob"])
        net_lock = 1.0 - first_price - opposite_target - 2 * fee - slippage
        mark_pnl = (current_first - first_price - fee) * quantity
        if current_opposite <= opposite_target:
            estimated_second_leg_cost = (opposite_target + fee + slippage) * quantity
        else:
            estimated_second_leg_cost = None
        total_net_lock_if_hit = net_lock * quantity
        action, reasons = action_for_position(position, match, risk_status, min_high_hit_probability)

        rows.append({
            "position_id": position.get("position_id"),
            "status": "open",
            "paper_only": True,
            "event_id": position.get("event_id"),
            "home_team": position.get("home_team") or match.get("home_team"),
            "away_team": position.get("away_team") or match.get("away_team"),
            "first_leg_outcome": position["first_leg_outcome"],
            "opposite_outcome": position["opposite_outcome"],
            "quantity": quantity,
            "first_leg_price": first_price,
            "opposite_target_price": opposite_target,
            "current_first_fair_prob": current_first,
            "current_opposite_fair_prob": current_opposite,
            "opposite_target_gap": current_opposite - opposite_target,
            "hit_probability": float(match.get("hit_probability") or 0.0),
            "expected_first_hit_minute": match.get("expected_first_hit_minute"),
            "net_locked_profit_per_contract_if_hit": net_lock,
            "total_net_locked_profit_if_hit": total_net_lock_if_hit,
            "mark_pnl_if_unhedged_now": mark_pnl,
            "estimated_second_leg_cost_if_ready": estimated_second_leg_cost,
            "expected_pnl_per_contract": match.get("expected_pnl_per_contract"),
            "latest_age_seconds": match.get("latest_age_seconds"),
            "action": action,
            "reasons": reasons,
        })

    ready = [row for row in rows if row.get("action") == "paper_second_leg_ready"]
    high_hit = [row for row in rows if row.get("action") == "watch_high_hit_probability"]
    blocked = [row for row in rows if str(row.get("action", "")).startswith("blocked")]

    return {
        "status": "ok" if not blocked else "blocked",
        "generated_at": utc_now(),
        "mode": "paper_position_tracking_only",
        "auto_trading_enabled": False,
        "risk_status": risk_status,
        "positions_configured": len(config.get("positions", [])),
        "positions_evaluated": len(rows),
        "ready_second_legs": len(ready),
        "high_hit_watchlist": len(high_hit),
        "blocked_positions": len(blocked),
        "positions": rows,
    }


def write_csv(path: Path, positions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "position_id",
        "action",
        "first_leg_outcome",
        "opposite_outcome",
        "quantity",
        "first_leg_price",
        "opposite_target_price",
        "current_first_fair_prob",
        "current_opposite_fair_prob",
        "opposite_target_gap",
        "hit_probability",
        "net_locked_profit_per_contract_if_hit",
        "total_net_locked_profit_if_hit",
        "mark_pnl_if_unhedged_now",
        "expected_pnl_per_contract",
        "latest_age_seconds",
        "reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for position in positions:
            row = {field: position.get(field) for field in fields}
            row["reasons"] = "|".join(position.get("reasons", []))
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Track paper-only first-leg positions against live hedge signals.")
    parser.add_argument("--positions", default="data/paper_positions/open_positions.json")
    parser.add_argument("--signals", default="data/reports/live_hedge_signals.json")
    parser.add_argument("--risk", default="data/reports/risk_status.json")
    parser.add_argument("--json-out", default="data/reports/paper_position_status.json")
    parser.add_argument("--csv-out", default="data/reports/paper_position_status.csv")
    parser.add_argument("--bootstrap-user-example", action="store_true")
    parser.add_argument("--min-high-hit-probability", type=float, default=0.75)
    args = parser.parse_args()

    positions_path = Path(args.positions)
    live_signals = load_json(Path(args.signals), {"status": "missing", "signals": []})
    risk = load_json(Path(args.risk), {"status": "missing"})

    if not positions_path.exists() and args.bootstrap_user_example:
        config = bootstrap_positions(positions_path, live_signals)
    else:
        config = load_json(positions_path, {"paper_only": True, "positions": []})

    report = evaluate_positions(config, live_signals, risk, args.min_high_hit_probability)
    save_json(Path(args.json_out), report)
    write_csv(Path(args.csv_out), report["positions"])

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"positions_config={positions_path}")
    print(f"saved {args.json_out}")
    print(f"saved {args.csv_out}")


if __name__ == "__main__":
    main()
