from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


def american_to_probability(odds: float) -> float:
    """Convert American odds to implied probability before vig removal."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def decimal_to_probability(odds: float) -> float:
    """Convert decimal odds to implied probability before vig removal."""
    if odds <= 1.0:
        raise ValueError("Decimal odds must be > 1.0")
    return 1.0 / odds


def normalize_remove_vig(raw_probs: Sequence[float]) -> list[float]:
    """Normalize probabilities so they sum to one; simple vig removal baseline."""
    s = float(sum(raw_probs))
    if s <= 0:
        raise ValueError("Sum of probabilities must be positive")
    return [float(p / s) for p in raw_probs]


def logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1 / (1 + np.exp(-x))


@dataclass(frozen=True)
class HedgeResult:
    first_leg_price: float
    second_leg_target: float
    gross_locked_profit_per_contract: float
    net_locked_profit_per_contract: float
    roi_on_cost: float


def hedge_lock_profit(first_leg_price: float, second_leg_target: float, fee_per_contract: float = 0.0) -> HedgeResult:
    """
    Binary market example:
    Buy outcome A at 0.40, later buy mutually exclusive outcome B at 0.40.
    Total payout is 1.00 no matter who wins, before fees/slippage.
    """
    gross = 1.0 - first_leg_price - second_leg_target
    net = gross - 2 * fee_per_contract
    cost = first_leg_price + second_leg_target + 2 * fee_per_contract
    roi = net / cost if cost > 0 else float("nan")
    return HedgeResult(first_leg_price, second_leg_target, gross, net, roi)


def simulate_threshold_hit_probability(
    current_prob: float,
    target_prob: float,
    minutes_remaining: float,
    vol_per_sqrt_min: float = 0.045,
    mean_reversion: float = 0.05,
    anchor_prob: float | None = None,
    n_paths: int = 20000,
    dt_minutes: float = 0.25,
    seed: int | None = None,
) -> dict:
    """
    Fast baseline price-path model on logit(probability).

    The model is intentionally simple: an Ornstein-Uhlenbeck-like process in logit space.
    Replace this with a learned volatility/drift model after collecting historical data.
    """
    if not (0 < current_prob < 1 and 0 < target_prob < 1):
        raise ValueError("current_prob and target_prob must be in (0,1)")
    if minutes_remaining <= 0:
        return {"hit_probability": float(current_prob <= target_prob), "expected_first_hit_minute": None}

    rng = np.random.default_rng(seed)
    steps = max(1, int(math.ceil(minutes_remaining / dt_minutes)))
    x = np.full(n_paths, logit(current_prob), dtype=np.float64)
    target_x = logit(target_prob)
    anchor_x = logit(anchor_prob if anchor_prob is not None else current_prob)

    hit = np.zeros(n_paths, dtype=bool)
    first_hit = np.full(n_paths, np.nan)
    sqrt_dt = math.sqrt(dt_minutes)

    for step in range(1, steps + 1):
        drift = mean_reversion * (anchor_x - x) * dt_minutes
        noise = vol_per_sqrt_min * sqrt_dt * rng.standard_normal(n_paths)
        x = x + drift + noise
        p = sigmoid(x)
        newly_hit = (~hit) & (p <= target_prob)
        first_hit[newly_hit] = step * dt_minutes
        hit |= newly_hit

    hit_probability = float(hit.mean())
    expected_first_hit = float(np.nanmean(first_hit)) if hit.any() else None
    return {
        "hit_probability": hit_probability,
        "expected_first_hit_minute": expected_first_hit,
        "paths": n_paths,
        "dt_minutes": dt_minutes,
        "model": "logit_OU_baseline",
    }
