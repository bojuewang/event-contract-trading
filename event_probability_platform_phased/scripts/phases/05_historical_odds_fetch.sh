#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/historical_odds data/reports

set -a
[[ -f .env ]] && source .env
set +a

KEY="${ODDS_API_KEY:-}"
if [[ -z "$KEY" || "$KEY" == "replace_me" || "$KEY" == "你的_the_odds_api_key" ]]; then
  echo "[05] 未设置 ODDS_API_KEY，生成历史训练 dry-run 样例，不调用外部 API。"
  PYTHONPATH=app python - <<'PY'
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(2026)
n = 5000
minutes_remaining = rng.uniform(1, 48, n)
score_diff = rng.normal(0, 10, n)
market_prob = np.clip(0.5 + score_diff / 60 + rng.normal(0, 0.08, n), 0.02, 0.98)
vol_5m = np.abs(rng.normal(0.04, 0.02, n))
target_hit_5m = rng.binomial(1, np.clip(0.15 + vol_5m * 3 + (0.5 - market_prob), 0.01, 0.95))
final_win = rng.binomial(1, market_prob)
df = pd.DataFrame({
    "event_id": [f"dry_hist_{i:06d}" for i in range(n)],
    "minutes_remaining": minutes_remaining,
    "score_diff": score_diff,
    "market_prob": market_prob,
    "vol_5m": vol_5m,
    "target_hit_5m": target_hit_5m,
    "final_win": final_win,
})
Path("data/historical_odds").mkdir(parents=True, exist_ok=True)
out = Path("data/historical_odds/dry_run_training_sample.csv")
df.to_csv(out, index=False)
print(f"[05] saved {out} rows={len(df)}")
PY
  echo "[05] dry-run 历史数据阶段完成。"
  exit 0
fi

SNAPSHOTS="${HISTORICAL_SNAPSHOT_ISO:-}"
if [[ -z "$SNAPSHOTS" ]]; then
  SNAPSHOTS=$(python - <<'PY'
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc).replace(microsecond=0)
print(",".join([(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"), (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")]))
PY
)
fi

echo "[05] 抓取历史 snapshots: $SNAPSHOTS"
export PYTHONPATH=app
python app/fetch_historical_odds.py --snapshots "$SNAPSHOTS" --out-dir data/historical_odds

echo "[05] 历史 API 阶段完成。"
