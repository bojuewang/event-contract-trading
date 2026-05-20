# Proposal：实时事件概率预测与对冲决策平台

## 1. 项目目标

建设一个低延迟、可训练、可回测的实时事件概率预测平台。平台接入实时赔率、预测市场订单簿、比赛 play-by-play、历史赔率和历史比赛数据，输出：

- 当前事件 fair probability。
- 未来价格触达某一阈值的概率。
- 对冲锁利可行性、预期收益、最大风险、成交失败风险。
- 数据延迟、盘口异常、模型置信度和风控告警。

示例：已买入骑士 0.40；若尼克斯跌到 0.40 且买入成功，二元互斥事件总成本为 0.80，理论 gross locked profit 为 0.20/份合约，未扣费用、滑点和无法成交风险。平台的核心不是只告诉你“现在是多少”，而是告诉你“尼克斯跌到 0.40 的概率、多久可能发生、错过/不发生的风险是多少”。

## 2. 数据源

### 第一阶段 MVP

- The Odds API：实时/即将开始赛事赔率、历史赔率快照。
- Polymarket：公共市场、订单簿、价格历史，用于预测市场型事件。
- NBA 官方/社区 API：低成本拉取赛程、基础统计，作为补充。

### 第二阶段生产增强

- Sportradar 或 SportsDataIO：实时 play-by-play、官方统计、伤病等。
- Kalshi：WebSocket 订单簿、成交、市场状态。
- 新闻/伤病/社媒：作为事件冲击因子，但必须做可信源过滤。

## 3. 系统架构

```text
Real-time APIs / WebSockets
        ↓
Ingestion Workers：异步轮询 + websocket
        ↓
Normalizer：统一 event_id、team_id、market_id、odds/probability
        ↓
Time-series Store：TimescaleDB/Postgres + Parquet
        ↓
Feature Engine：盘口、波动率、比分、时间、伤病、成交量、订单簿深度
        ↓
Model Service：win probability + threshold hit probability + calibration
        ↓
Decision API：对冲信号、风险等级、告警
        ↓
Dashboard / Alert：Web UI、短信/Discord/Telegram/Email
```

## 4. 模型设计

### 4.1 当前胜率模型

优先使用市场隐含概率作为 baseline：

- decimal odds: `p_raw = 1 / odds`
- American odds: `+x => 100/(x+100)`；`-x => x/(x+100)`
- 去水：`p_fair_i = p_raw_i / sum(p_raw)`

然后融合 live features：比分、时间、回合、犯规、主客场、赛前强弱、伤病、赔率移动、订单簿深度。

第一版模型建议：`LightGBM/XGBoost/HistGradientBoosting + isotonic calibration`。数据足够后再上 PyTorch GRU/Transformer。

### 4.2 价格触达模型

你的策略真正需要的是：

`P(opposite_price <= target_price before settlement | current_state)`

第一版使用 logit 概率空间的随机过程：

- 当前概率 `p` 转成 `logit(p)`。
- 估计盘口波动率、均值回归、跳跃风险。
- Monte Carlo 模拟价格路径，输出触达概率和首次触达时间。

第二版用历史数据训练条件模型：

- 输入：当前概率、赔率变化速度、剩余时间、比分、成交量、盘口深度、伤病事件。
- 标签：未来 T 分钟内是否触达目标价。
- 输出：触达概率、置信区间、推荐等待/退出动作。

## 5. 刷新频率目标

- 预测市场 WebSocket：目标 0.5–1 秒更新一次 UI。
- 体育实时赔率：受 API 套餐和限频影响，MVP 先 3–10 秒轮询。
- 模型 inference：1 秒内完成。
- 历史训练：每日/每场赛后增量训练。
- 高频盘口交易不建议直接依赖免费/低价 API；生产级需要专门低延迟 data feed。

## 6. GPU 方案

RTX 5070 适合：

- 大批量 Monte Carlo 并行模拟。
- PyTorch 序列模型训练。
- 多事件并发 inference。

不需要 GPU 的部分：HTTP/WebSocket 采集、去水、简单 tabular 模型、数据库写入。

## 7. 风控原则

- 不做自动下单，只输出信号。
- 必须计入 fees、slippage、盘口深度、成交概率。
- 数据源延迟超过阈值时暂停信号。
- 盘口异常/比赛暂停/伤病未确认时降低置信度。
- 每个策略必须经过历史回测和纸面交易。

## 8. 交付计划

### Week 1：MVP 数据与 dashboard

- 搭建 Postgres/Redis。
- 接入 The Odds API。
- 实现赔率转概率、去水、当前概率展示。
- 实现对冲收益计算和阈值触达模拟。

### Week 2：历史数据与模型

- 拉取历史 odds snapshots。
- 整合比赛结果/play-by-play。
- 训练 baseline win probability model。
- 做 calibration 和 Brier/log-loss 评估。

### Week 3：策略回测

- 回测“第一腿买入 + 等第二腿目标价”的策略。
- 输出触达率、平均等待时间、锁利率、最大亏损、错过率。
- 加入手续费、滑点、盘口深度限制。

### Week 4：生产化

- 加入 WebSocket 数据源。
- 加入告警系统。
- GPU 加速 Monte Carlo。
- 完成监控、日志和风控开关。

