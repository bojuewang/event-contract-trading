from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from config import get_settings
from odds_math import hedge_lock_profit, simulate_threshold_hit_probability

st.set_page_config(page_title="实时事件概率预测", layout="wide")
st.title("实时事件概率预测与对冲信号")

settings = get_settings()

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
