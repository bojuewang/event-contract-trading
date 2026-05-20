from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from odds_math import simulate_threshold_hit_probability


def cpu_benchmark(paths: int, minutes: float, seed: int) -> dict:
    t0 = time.perf_counter()
    result = simulate_threshold_hit_probability(
        current_prob=0.60,
        target_prob=0.40,
        minutes_remaining=minutes,
        vol_per_sqrt_min=0.045,
        mean_reversion=0.05,
        n_paths=paths,
        dt_minutes=0.25,
        seed=seed,
    )
    elapsed = time.perf_counter() - t0
    result.update({"device": "cpu_numpy", "elapsed_seconds": elapsed, "paths_per_second": paths / elapsed})
    return result


def gpu_benchmark(paths: int, minutes: float, seed: int) -> dict | None:
    try:
        import torch
    except Exception as exc:
        return {"device": "cuda", "available": False, "reason": f"torch import failed: {exc}"}
    if not torch.cuda.is_available():
        return {"device": "cuda", "available": False, "reason": "torch.cuda.is_available() is False"}

    torch.manual_seed(seed)
    device = torch.device("cuda")
    dt = 0.25
    steps = max(1, int(math.ceil(minutes / dt)))
    current_prob = 0.60
    target_prob = 0.40
    vol = 0.045
    mean_reversion = 0.05

    def logit(p: float) -> float:
        return math.log(p / (1.0 - p))

    x = torch.full((paths,), logit(current_prob), dtype=torch.float32, device=device)
    target_x = logit(target_prob)
    anchor_x = logit(current_prob)
    hit = torch.zeros(paths, dtype=torch.bool, device=device)
    sqrt_dt = math.sqrt(dt)

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(steps):
        drift = mean_reversion * (anchor_x - x) * dt
        noise = vol * sqrt_dt * torch.randn(paths, dtype=torch.float32, device=device)
        x = x + drift + noise
        p = torch.sigmoid(x)
        hit |= p <= target_prob
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0
    return {
        "device": torch.cuda.get_device_name(0),
        "available": True,
        "hit_probability": float(hit.float().mean().item()),
        "paths": paths,
        "minutes": minutes,
        "elapsed_seconds": elapsed,
        "paths_per_second": paths / elapsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paths", type=int, default=200_000)
    parser.add_argument("--minutes", type=float, default=24.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/reports/gpu_monte_carlo_benchmark.json")
    args = parser.parse_args()

    cpu = cpu_benchmark(args.paths, args.minutes, args.seed)
    gpu = gpu_benchmark(args.paths, args.minutes, args.seed)
    report = {"cpu": cpu, "gpu": gpu}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
