from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from odds_math import hedge_lock_profit, simulate_threshold_hit_probability

app = FastAPI(title="Realtime Event Probability API", version="0.1.0")


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


@app.post("/hedge/lock-profit")
def hedge(req: HedgeRequest) -> dict:
    result = hedge_lock_profit(req.first_leg_price, req.second_leg_target, req.fee_per_contract)
    return result.__dict__


@app.post("/simulate/threshold")
def simulate(req: ThresholdRequest) -> dict:
    return simulate_threshold_hit_probability(**req.model_dump())
