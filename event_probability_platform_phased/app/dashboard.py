from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from config import get_settings
from odds_math import hedge_lock_profit, simulate_threshold_hit_probability

st.set_page_config(page_title="实时事件概率预测", layout="wide")
st.title("实时事件概率预测与对冲信号")

settings = get_settings()
risk_path = Path("data/reports/risk_status.json")

if risk_path.exists():
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    risk_status = risk.get("status", "unknown")
    if risk_status == "ok":
        st.success("风控状态：OK。当前仅启用 paper-trade 信号展示。")
    elif risk_status == "warn":
        st.warning("风控状态：WARN。信号可观察，但需要检查警告项。")
    else:
        st.error("风控状态：BLOCKED。暂停使用信号。")
    with st.expander("风控详情", expanded=risk_status != "ok"):
        st.json(risk)
else:
    st.warning("尚未生成 risk_status.json。运行 Phase 16 后会显示风控状态。")

with st.sidebar:
    st.header("对冲参数")
    first = st.slider("已买入价格", 0.01, 0.99, 0.40, 0.01)
    target = st.slider("第二腿目标价格", 0.01, 0.99, 0.40, 0.01)
    fee = st.number_input("每份合约费用", min_value=0.0, value=0.0, step=0.001)
    current_prob = st.slider("当前对手概率", 0.01, 0.99, 0.60, 0.01)
    minutes_remaining = st.number_input("剩余分钟", min_value=0.1, value=48.0, step=1.0)
    vol = st.number_input("波动率 / sqrt(min)", min_value=0.001, value=settings.default_vol_per_sqrt_min, step=0.001)

hedge = hedge_lock_profit(first, target, fee)
col1, col2, col3 = st.columns(3)
col1.metric("Gross locked profit", f"{hedge.gross_locked_profit_per_contract:.4f}")
col2.metric("Net locked profit", f"{hedge.net_locked_profit_per_contract:.4f}")
col3.metric("ROI on cost", f"{hedge.roi_on_cost:.2%}")

sim = simulate_threshold_hit_probability(
    current_prob=current_prob,
    target_prob=target,
    minutes_remaining=minutes_remaining,
    vol_per_sqrt_min=vol,
    n_paths=min(settings.monte_carlo_paths, 50000),
)
st.metric("第二腿触达目标价概率", f"{sim['hit_probability']:.2%}")
st.json(sim)

st.subheader("实时对冲信号")
signals_path = Path("data/reports/live_hedge_signals.json")
alerts_path = Path("data/alerts/hedge_signal_alerts.jsonl")
paper_positions_path = Path("data/reports/paper_position_status.json")

if signals_path.exists():
    report = json.loads(signals_path.read_text(encoding="utf-8"))
    signals = report.get("signals", [])
    candidates = [item for item in signals if item.get("signal") == "paper_trade_candidate"]
    watches = [item for item in signals if item.get("signal") == "watch"]
    rejects = [item for item in signals if item.get("signal") == "reject"]
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("信号更新时间", report.get("generated_at", "n/a"))
    s2.metric("候选", len(candidates))
    s3.metric("观察", len(watches))
    s4.metric("拒绝", len(rejects))
    if signals:
        df_signals = pd.DataFrame(signals)
        df_signals["reasons"] = df_signals["reasons"].apply(lambda items: ", ".join(items) if isinstance(items, list) else items)
        cols = [
            "signal",
            "home_team",
            "away_team",
            "first_leg_outcome",
            "opposite_outcome",
            "current_first_fair_prob",
            "current_opposite_fair_prob",
            "hit_probability",
            "expected_pnl_per_contract",
            "net_locked_profit_if_hit",
            "latest_age_seconds",
            "reasons",
        ]
        st.dataframe(df_signals[[c for c in cols if c in df_signals.columns]], use_container_width=True)
else:
    st.info("尚未生成 live_hedge_signals.json。运行 Phase 13 或 Phase 14 后这里会显示信号。")

st.subheader("纸面持仓追踪")
if paper_positions_path.exists():
    paper_report = json.loads(paper_positions_path.read_text(encoding="utf-8"))
    positions = paper_report.get("positions", [])
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("纸面持仓", paper_report.get("positions_evaluated", 0))
    p2.metric("第二腿可执行", paper_report.get("ready_second_legs", 0))
    p3.metric("高触达观察", paper_report.get("high_hit_watchlist", 0))
    p4.metric("风控状态", paper_report.get("risk_status", "n/a"))
    if positions:
        df_positions = pd.DataFrame(positions)
        df_positions["reasons"] = df_positions["reasons"].apply(lambda items: ", ".join(items) if isinstance(items, list) else items)
        cols = [
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
            "mark_pnl_if_unhedged_now",
            "latest_age_seconds",
            "reasons",
        ]
        st.dataframe(df_positions[[c for c in cols if c in df_positions.columns]], use_container_width=True)
else:
    st.info("尚未生成 paper_position_status.json。运行 Phase 17 后这里会显示纸面持仓追踪。")

st.subheader("最近 alert")
if alerts_path.exists():
    lines = [line for line in alerts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    alerts = [json.loads(line) for line in lines[-20:]]
    if alerts:
        st.dataframe(pd.DataFrame(alerts), use_container_width=True)
    else:
        st.caption("alert 日志为空。")
else:
    st.caption("尚未生成 alert 日志。")

st.subheader("最近采集的赔率 ticks")
try:
    sync_url = settings.database_url.replace("postgresql+psycopg", "postgresql+psycopg")
    engine = create_engine(sync_url)
    query = text("""
        SELECT source, event_id, market, outcome, ingested_at, price, raw_prob, fair_prob, meta
        FROM event_ticks
        ORDER BY ingested_at DESC
        LIMIT 200
    """)
    df = pd.read_sql(query, engine)
    st.dataframe(df, use_container_width=True)
except Exception as exc:
    st.warning(f"数据库暂不可读：{exc}")
