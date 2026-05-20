# 实时事件概率预测与对冲决策平台 Starter Kit

这个 starter kit 用于搭建一个 MVP：实时接入赔率/预测市场/比赛数据，统一转成 fair probability，并输出“是否值得做第二腿对冲”的概率信号。

> 重要：本项目只做数据分析、概率预测和风控信号，不提供自动下注/下单功能。使用前请确认当地法律、平台条款、数据授权和税务要求。

## 核心目标

给定一个事件，例如“骑士胜出 / 尼克斯胜出”，系统每秒或准实时输出：

1. 当前 fair win probability：去除 vig / spread 后的真实近似概率。
2. 价格路径风险：例如 `P(尼克斯价格在比赛结束前跌到 0.40 | 当前状态)`。
3. 对冲锁利判断：例如已买骑士 0.40，如果尼克斯可以在 0.40 买到，则 gross locked profit = `1 - 0.40 - 0.40 = 0.20`，再扣交易费、滑点和成交失败风险。
4. 风控状态：是否暂停、是否数据延迟、是否盘口断流、是否模型置信度不足。

## 目录

```text
app/
  api.py                    FastAPI 接口
  config.py                 环境变量配置
  odds_math.py              赔率、概率、对冲、路径模拟工具
  storage.py                PostgreSQL/TimescaleDB 写入
  ingest_odds.py            The Odds API 实时轮询样例
  dashboard.py              Streamlit 简易仪表盘
  gpu_check.py              GPU/CUDA 检查
  train_baseline.py         基线模型训练样例
  clients/
    the_odds_api.py         The Odds API 客户端
    polymarket.py           Polymarket 公共市场数据客户端样例
    kalshi_ws.py            Kalshi WebSocket 结构样例
scripts/
  bootstrap.sh              创建虚拟环境并安装依赖
  run_api.sh                启动 API
  run_ingest_odds.sh        启动赔率采集
  run_dashboard.sh          启动 dashboard
  install_gpu_pytorch.sh    安装 PyTorch CUDA 版本样例
  init_db.sql               数据库 schema
docker-compose.yml          Postgres + Redis
.env.example                API key 和配置模板
```

## 快速开始

```bash
cd event_probability_platform_starter
cp .env.example .env
# 修改 .env：至少填入 ODDS_API_KEY

docker compose up -d
bash scripts/bootstrap.sh
source .venv/bin/activate
python app/gpu_check.py

# 终端 1：启动 API
bash scripts/run_api.sh

# 终端 2：启动实时赔率采集
bash scripts/run_ingest_odds.sh

# 终端 3：启动仪表盘
bash scripts/run_dashboard.sh
```

## GPU / RTX 5070 建议

- 数据采集、去水、简单概率计算：CPU 足够。
- 历史训练、Monte Carlo 批量路径模拟、深度序列模型：使用 GPU。
- PyTorch CUDA 安装请以 PyTorch 官网 selector 为准；本项目提供 `scripts/install_gpu_pytorch.sh` 作为样例。

## API 来源建议

- The Odds API：实时/历史赔率快照，适合快速 MVP。
- Sportradar / SportsDataIO：付费实时比赛数据、play-by-play、伤病等，适合生产级。
- Kalshi / Polymarket：预测市场价格和 order book，适合泛事件市场。

## 生产化路线

MVP 可以先用轮询 + Postgres。生产版建议升级为：

- WebSocket 优先，HTTP 轮询兜底。
- Redpanda/Kafka 作为事件总线。
- TimescaleDB 存价格时间序列，S3/MinIO 存 Parquet 历史数据。
- Redis 做当前概率缓存。
- 模型输出必须做 calibration、backtest、latency monitoring。

