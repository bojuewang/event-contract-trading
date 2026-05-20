# 阶段门控版：实时事件概率预测与对冲判断平台

这个版本把项目拆成 10 个阶段。每个阶段执行完之后，只会进入 `completed` 状态，不会自动进入下一阶段。你必须检查输出和日志，然后执行确认指令。确认通过后，才允许运行下一阶段。

设计目标来自 proposal：平台需要接入实时赔率、预测市场订单簿、比赛 play-by-play、历史赔率和历史比赛数据，输出当前 fair probability、未来价格触达阈值的概率、对冲锁利可行性与风控告警。你的 40/40 例子本质是：第一腿买入后，判断第二腿目标价是否可能触达，以及触达后净锁利是否覆盖费用、滑点和成交失败风险。

## 一键查看阶段

```bash
python3 phase_runner.py list
```

## 标准运行方式

从项目根目录开始：

```bash
python3 phase_runner.py run-next
```

阶段执行成功后，终端会显示类似：

```bash
阶段 00_preflight 已执行完成，但尚未进入下一阶段。
请检查终端输出和日志，确认通过后执行：
  python phase_runner.py confirm 00_preflight --token CONFIRM-00_preflight-xxxxxxx
确认后再执行：
  python phase_runner.py run-next
```

确认：

```bash
python3 phase_runner.py confirm 00_preflight --token CONFIRM-00_preflight-xxxxxxx
```

继续下一阶段：

```bash
python3 phase_runner.py run-next
```

也可以使用 wrapper：

```bash
scripts/run_next_phase.sh
scripts/confirm_phase.sh 00_preflight CONFIRM-00_preflight-xxxxxxx
scripts/phase_status.sh
```

## 阶段说明

| 阶段 | 作用 |
|---|---|
| 00_preflight | 检查 Python、Docker、curl、GPU 可见性和目录结构 |
| 01_bootstrap_env | 创建 .venv、安装依赖、创建 .env |
| 02_services_db | 启动 Postgres/Redis 并检查 event_ticks 表 |
| 03_probability_api | 启动 FastAPI，测试锁利计算和阈值触达模拟 |
| 04_realtime_odds_ingestion | 启动实时赔率采集；无 API key 时 dry-run |
| 05_historical_odds_fetch | 抓取历史 odds snapshots；无 API key 时生成训练样例 |
| 06_gpu_monte_carlo_check | 检查 RTX/CUDA/PyTorch，运行 Monte Carlo benchmark |
| 07_train_baseline_model | 训练 baseline win probability model |
| 08_backtest_threshold_strategy | 回测 40/40 第二腿目标价触达策略 |
| 09_dashboard_alerts | 启动 dashboard 并检查 API/模型/数据状态 |
| 10_readiness_report | 生成生产化就绪报告 |
| 11_real_data_keys_and_ingestion | 配置真实 ODDS_API_KEY 后，拉取实时赔率并写入 event_ticks |

## 重要环境变量

编辑 `.env`：

```bash
ODDS_API_KEY=你的_key
ODDS_API_SPORT=basketball_nba
ODDS_API_REGIONS=us
ODDS_API_MARKETS=h2h
ODDS_API_ODDS_FORMAT=decimal
ODDS_API_POLL_SECONDS=5
```

可选运行参数：

```bash
API_PORT=8000
DASHBOARD_PORT=8501
MC_BENCHMARK_PATHS=200000
BACKTEST_EVENTS=20000
FIRST_LEG_PRICE=0.40
OPPOSITE_START_PRICE=0.60
OPPOSITE_TARGET_PRICE=0.40
FEE_PER_CONTRACT=0.00
SLIPPAGE_PER_LEG=0.005
HISTORICAL_SNAPSHOT_ISO=2026-05-19T20:00:00Z,2026-05-19T21:00:00Z
```

## 状态文件和日志

- 阶段状态：`.phase_state.json`
- 阶段日志：`logs/<phase_id>.<timestamp>.log`
- API 日志：`logs/api.log`
- 实时采集日志：`logs/ingest_odds.log`
- Dashboard 日志：`logs/dashboard.log`
- readiness 报告：`data/reports/readiness_report.md`

## 重跑和停止

重跑某阶段：

```bash
python3 phase_runner.py run 04_realtime_odds_ingestion --rerun
```

重置某阶段状态：

```bash
python3 phase_runner.py reset --phase 04_realtime_odds_ingestion
```

停止后台 API / dashboard / ingest worker：

```bash
scripts/stop_runtime.sh
```

停止数据库和 Redis：

```bash
docker compose down
```

## 执行纪律

不要直接跳过确认。平台的每一阶段都可能启动服务、写入数据库、生成模型文件或产生回测结果。确认机制是为了确保：上一阶段输出正确、日志无重大错误、配置无误、数据没有延迟或污染，然后才进入下一阶段。
