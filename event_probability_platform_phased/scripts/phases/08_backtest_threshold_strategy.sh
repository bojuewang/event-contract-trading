#!/usr/bin/env bash
set -euo pipefail

ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
source .venv/bin/activate
mkdir -p data/backtests data/reports

echo "[08] 回测 40/40 第二腿阈值触达策略"
export PYTHONPATH=app
python app/backtest_threshold_strategy.py \
  --n-events "${BACKTEST_EVENTS:-20000}" \
  --first-leg-price "${FIRST_LEG_PRICE:-0.40}" \
  --opposite-start-price "${OPPOSITE_START_PRICE:-0.60}" \
  --opposite-target-price "${OPPOSITE_TARGET_PRICE:-0.40}" \
  --fee-per-contract "${FEE_PER_CONTRACT:-0.00}" \
  --slippage-per-leg "${SLIPPAGE_PER_LEG:-0.005}" \
  --minutes-remaining "${MINUTES_REMAINING:-36}" \
  --out-dir data/backtests | tee data/reports/backtest_threshold_strategy.txt

echo "[08] 回测结果文件"
ls -lh data/backtests/threshold_40_40_backtest.csv data/backtests/threshold_40_40_metrics.json

echo "[08] 回测阶段完成。"
