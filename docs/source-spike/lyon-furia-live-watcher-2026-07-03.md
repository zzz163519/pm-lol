# LYON vs FURIA Live Watcher Smoke

- 采集窗口：`2026-07-03T16:28:32.171348Z` -> `2026-07-03T16:38:47.052875Z`
- JSONL：`docs/source-spike/lyon-furia-live-watcher-2026-07-03.jsonl`
- 样本数：43
- LoLEsports eventState：['unstarted']
- livestats window status 分布：{None: 1, 204: 214}
- livestats details status 分布：{204: 215}
- Polymarket orderbook 可读样本数：42/43
- 是否可计算 LoLEsports source latency：False

## 结论

- 本窗口内未拿到 LoLEsports livestats body/sourceTimestamp，不能计算 live latency。
- LoLEsports schedule/eventDetails 至少部分样本仍为 `unstarted`。
- livestats window 存在 204/no body，不能宣称 live validation passed。
- Polymarket CLOB orderbook 在采集窗口内可读。
- 本次只读 watcher 不构成策略、信号、下单或 Phase 0 完成证明。
