from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def simulate_backtest(
    n_events: int,
    first_leg_price: float,
    opposite_start_price: float,
    opposite_target_price: float,
    fee_per_contract: float,
    slippage_per_leg: float,
    minutes_remaining: float,
    vol_per_sqrt_min: float,
    mean_reversion: float,
    seed: int,
) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    dt = 0.25
    steps = max(1, int(math.ceil(minutes_remaining / dt)))

    x = np.full(n_events, logit(opposite_start_price), dtype=np.float64)
    anchor = logit(opposite_start_price)
    target = opposite_target_price
    hit = np.zeros(n_events, dtype=bool)
    first_hit_min = np.full(n_events, np.nan)

    # 每场比赛不同波动率，模拟盘口差异、暂停、犯规潮、伤病信息等冲击。
    event_vol = np.clip(rng.normal(vol_per_sqrt_min, vol_per_sqrt_min * 0.35, n_events), 0.005, 0.25)
    event_drift_bias = rng.normal(0.0, 0.015, n_events)

    for step in range(1, steps + 1):
        drift = mean_reversion * (anchor - x) * dt + event_drift_bias * dt
        noise = event_vol * math.sqrt(dt) * rng.standard_normal(n_events)
        jump_mask = rng.random(n_events) < 0.004
        jumps = jump_mask * rng.normal(0, 0.35, n_events)
        x = x + drift + noise + jumps
        p = sigmoid(x)
        newly = (~hit) & (p <= target)
        first_hit_min[newly] = step * dt
        hit |= newly

    final_opposite_prob = sigmoid(x)
    first_outcome_true_prob = 1.0 - final_opposite_prob
    first_leg_wins = rng.random(n_events) < first_outcome_true_prob

    gross_locked_profit = 1.0 - first_leg_price - opposite_target_price
    net_locked_profit = gross_locked_profit - 2 * fee_per_contract - slippage_per_leg

    # 如果第二腿没有触达，仍只持有第一腿：赢则 1 - 成本；输则亏掉成本。
    unhedged_win_profit = 1.0 - first_leg_price - fee_per_contract
    unhedged_loss_profit = -first_leg_price - fee_per_contract

    pnl = np.where(hit, net_locked_profit, np.where(first_leg_wins, unhedged_win_profit, unhedged_loss_profit))
    df = pd.DataFrame({
        "event_id": [f"sim_{i:06d}" for i in range(n_events)],
        "hit_second_leg": hit,
        "first_hit_minute": first_hit_min,
        "final_opposite_prob": final_opposite_prob,
        "first_leg_wins_if_unhedged": first_leg_wins,
        "pnl_per_contract": pnl,
    })
    equity = df["pnl_per_contract"].cumsum()
    running_max = equity.cummax()
    drawdown = equity - running_max

    metrics = {
        "n_events": int(n_events),
        "first_leg_price": first_leg_price,
        "opposite_start_price": opposite_start_price,
        "opposite_target_price": opposite_target_price,
        "fee_per_contract": fee_per_contract,
        "slippage_per_leg": slippage_per_leg,
        "hit_rate": float(df["hit_second_leg"].mean()),
        "average_first_hit_minute": None if df["first_hit_minute"].dropna().empty else float(df["first_hit_minute"].mean(skipna=True)),
        "gross_locked_profit_if_hit": gross_locked_profit,
        "net_locked_profit_if_hit": net_locked_profit,
        "average_pnl_per_contract": float(df["pnl_per_contract"].mean()),
        "median_pnl_per_contract": float(df["pnl_per_contract"].median()),
        "positive_pnl_rate": float((df["pnl_per_contract"] > 0).mean()),
        "max_drawdown_per_contract_sequence": float(drawdown.min()),
    }
    return df, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest 40/40 threshold hedge strategy with simulated paths.")
    parser.add_argument("--n-events", type=int, default=20000)
    parser.add_argument("--first-leg-price", type=float, default=0.40)
    parser.add_argument("--opposite-start-price", type=float, default=0.60)
    parser.add_argument("--opposite-target-price", type=float, default=0.40)
    parser.add_argument("--fee-per-contract", type=float, default=0.00)
    parser.add_argument("--slippage-per-leg", type=float, default=0.005)
    parser.add_argument("--minutes-remaining", type=float, default=36.0)
    parser.add_argument("--vol-per-sqrt-min", type=float, default=0.045)
    parser.add_argument("--mean-reversion", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-dir", default="data/backtests")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df, metrics = simulate_backtest(
        n_events=args.n_events,
        first_leg_price=args.first_leg_price,
        opposite_start_price=args.opposite_start_price,
        opposite_target_price=args.opposite_target_price,
        fee_per_contract=args.fee_per_contract,
        slippage_per_leg=args.slippage_per_leg,
        minutes_remaining=args.minutes_remaining,
        vol_per_sqrt_min=args.vol_per_sqrt_min,
        mean_reversion=args.mean_reversion,
        seed=args.seed,
    )
    csv_path = out_dir / "threshold_40_40_backtest.csv"
    json_path = out_dir / "threshold_40_40_metrics.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"saved {csv_path}")
    print(f"saved {json_path}")


if __name__ == "__main__":
    main()
