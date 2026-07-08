# pm-lol — Hermes 项目规则

## 项目定位

pm-lol 是 Polymarket LOL 价值交易系统，目标是先验证自动数据输入闭环，再建设行情、比赛状态和只读数据底座。

系统当前不是实盘交易系统，不接钱包、不保存私钥、不调用真实下单接口。

## 当前阶段

当前阶段：Conditional Phase 1 Data Foundation。

这不是 full Phase 1，也不是策略、信号、纸面交易或执行层启动许可。当前只允许继续
Data Foundation 范围内的 market/orderbook REST polling、LOL source parser、
schema/storage、resolver hard gate、collector run 记录和 replay 验证。

本阶段只验证：
- Polymarket LOL Game Winner 市场发现、orderbook 和行情读取是否稳定。
- Cito + LoLEsports 或等效实时源组合是否能稳定提供 final picks、game clock、gold、objectives。
- 赛程、队伍别名、局数和 Polymarket 市场是否能可靠映射。

Conditional Phase 1 完成前，禁止新增 strategy / edge / signal / paper trading /
wallet / private key / order 相关实现或配置。

## 工作范围和数据源策略

- 当前主源组合：Cito API 覆盖 team identity / gold / objectives / kills /
  gameClock / gameState；LoLEsports Frontend API 补充 draft/picks。仍需多场次
  freshness/stability 复核，未通过前不得视为生产安全。
- 盘口源：Polymarket public REST/orderbook polling 是 QuoteRecorder v1 baseline；
  WebSocket deferred，待 clean network retest。
- 商业备选：PandaScore / GRID / Abios。
- Oracle's Elixir 只用于历史研究，不作为 live 输入。
- 每个 source spike 必须留下原始响应样例、字段清单、延迟记录、限制说明和结论。

## Agent 注意事项

- 默认只做只读验证、数据采集、schema 草案和证据整理。
- 禁止 strategy / edge / signal / paper trading / wallet / private key / order。
- 不接私钥、不接钱包、不写真实下单、不输出执行许可。
- API key / token 只能走受控 secret 注入，不得贴 issue 评论、不得写入 artifact；
  一旦泄露必须立即轮换。
- 代码类卡不能只靠本地脏树验收：必须有 PR；无 PR 不验收。文档类卡也优先走 PR，
  若只做评论不改 repo，必须在结果中明确说明。
- 映射置信度低于门槛时跳过，不用代码绕过约束。
- 任何源失败都记录失败原因，不伪造 fallback 成功。
- 进入下一阶段前必须检查 `roadmap.md`、`tasks.md`、`docs/source-score.md` 和 `docs/decision-log.md`。
