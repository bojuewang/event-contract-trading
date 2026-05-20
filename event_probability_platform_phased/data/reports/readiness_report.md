# 实时事件概率预测平台：阶段化就绪报告

生成时间：2026-05-20T00:56:08Z

## 服务状态

| 项目 | 状态 |
|---|---|
| FastAPI | UP |
| Dashboard | UP |
| Postgres | UP |
| Redis | UP |
| event_ticks rows | 0 |

## 模型与回测状态

| 项目 | 状态 |
|---|---|
| baseline_winprob.joblib | present |
| threshold_40_40_metrics.json | present |
| gpu_monte_carlo_benchmark.json | present |

## 风控开关建议

- 数据延迟超过阈值：暂停信号。
- 没有订单簿深度或盘口断流：不输出可执行机会。
- second leg 目标价触达概率不足：只观察，不执行。
- fees + slippage 后净锁利 <= 0：禁止信号。
- 未完成历史回测和纸面交易：不做自动下单。

## 下一步生产化任务

1. 接入真实 WebSocket orderbook 数据源。
2. 用真实历史 odds snapshots + play-by-play 替换 dry-run 训练样例。
3. 将阈值触达模型从模拟过程升级为监督学习模型。
4. 加入 Telegram/Discord/Email alert。
5. 加入数据延迟、盘口异常、成交深度、模型置信度四类风控监控。
