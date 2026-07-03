# pm-lol — Hermes 项目规则

## 项目定位

pm-lol 是 Polymarket LOL 价值交易系统，目标是先验证自动数据输入闭环，再建设行情、比赛状态和纸面验证底座。

系统当前不是实盘交易系统，不接钱包、不保存私钥、不调用真实下单接口。

## 当前阶段

当前阶段：Phase 0 — Source Feasibility Spike。

本阶段只验证：
- Polymarket LOL Game Winner 市场发现、orderbook 和行情读取是否稳定。
- LoLEsports 或等效实时源是否能自动提供 final picks、game clock、gold、objectives。
- 赛程、队伍别名、局数和 Polymarket 市场是否能可靠映射。

Phase 0 完成前，不写策略、不建预测模型、不生成交易信号、不启动 Phase 1 代码骨架。

## 工作范围和数据源策略

- 主 spike 源：LoLEsports Frontend API；live latency 未验证前不得视为生产安全。
- 盘口源：Polymarket public REST/orderbook；WebSocket 仍需复测。
- 商业备选：PandaScore；未来升级：GRID。
- Oracle's Elixir 只用于历史研究，不作为 live 输入。
- Cito / 非官方源当前不推荐作为 Phase 1 主源或备源。
- 每个 source spike 必须留下原始响应样例、字段清单、延迟记录、限制说明和结论。

## Agent 注意事项

- 默认只做只读验证、数据采集、schema 草案和证据整理。
- 不接私钥、不接钱包、不写真实下单、不输出执行许可。
- 映射置信度低于门槛时跳过，不用代码绕过约束。
- 任何源失败都记录失败原因，不伪造 fallback 成功。
- 进入下一阶段前必须检查 `roadmap.md`、`tasks.md`、`docs/source-score.md` 和 `docs/decision-log.md`。
