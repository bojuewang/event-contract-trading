from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from odds_math import hedge_lock_profit, simulate_threshold_hit_probability

app = FastAPI(title="Realtime Event Probability API", version="0.1.0")
ROOT = Path(__file__).resolve().parent.parent
LIVE_SIGNALS_PATH = ROOT / "data" / "reports" / "live_hedge_signals.json"
ALERTS_PATH = ROOT / "data" / "alerts" / "hedge_signal_alerts.jsonl"
RISK_STATUS_PATH = ROOT / "data" / "reports" / "risk_status.json"


class HedgeRequest(BaseModel):
    first_leg_price: float = Field(gt=0, lt=1, description="Price paid for first mutually exclusive outcome")
    second_leg_target: float = Field(gt=0, lt=1, description="Target price for opposite outcome")
    fee_per_contract: float = Field(default=0.0, ge=0)


class ThresholdRequest(BaseModel):
    current_prob: float = Field(gt=0, lt=1)
    target_prob: float = Field(gt=0, lt=1)
    minutes_remaining: float = Field(gt=0)
    vol_per_sqrt_min: float = Field(default=0.045, gt=0)
    mean_reversion: float = Field(default=0.05, ge=0)
    anchor_prob: float | None = Field(default=None, gt=0, lt=1)
    n_paths: int = Field(default=20000, ge=1000, le=500000)
    seed: int | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/signals/live")
def live_signals() -> dict:
    if not LIVE_SIGNALS_PATH.exists():
        return {"status": "missing", "path": str(LIVE_SIGNALS_PATH)}
    return json.loads(LIVE_SIGNALS_PATH.read_text(encoding="utf-8"))


@app.get("/alerts/recent")
def recent_alerts(limit: int = 20) -> dict:
    limit = max(1, min(limit, 200))
    if not ALERTS_PATH.exists():
        return {"status": "missing", "alerts": []}
    lines: deque[str] = deque(maxlen=limit)
    with ALERTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                lines.append(line)
    alerts = [json.loads(line) for line in lines]
    return {"status": "ok", "count": len(alerts), "alerts": alerts}


@app.get("/risk/status")
def risk_status() -> dict:
    if not RISK_STATUS_PATH.exists():
        return {"status": "missing", "path": str(RISK_STATUS_PATH)}
    return json.loads(RISK_STATUS_PATH.read_text(encoding="utf-8"))


@app.post("/hedge/lock-profit")
def hedge(req: HedgeRequest) -> dict:
    result = hedge_lock_profit(req.first_leg_price, req.second_leg_target, req.fee_per_contract)
    return result.__dict__


@app.post("/simulate/threshold")
def simulate(req: ThresholdRequest) -> dict:
    return simulate_threshold_hit_probability(**req.model_dump())
