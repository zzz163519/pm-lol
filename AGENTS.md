# pm-lol — Hermes 项目规则

## 项目定位

pm-lol 是 Polymarket LOL 价值交易系统，目标是先验证自动数据输入闭环，再建设行情、比赛状态和只读数据底座。

系统当前不是实盘交易系统，不接钱包、不保存私钥、不调用真实下单接口。

## 当前阶段

当前阶段：Phase 0 — Automated Visual Source Qualification。

当前只允许建设完成连续两场数据源验收所需的最小纯代码视觉提取 spike：HLS 抓帧、
固定 ROI、英雄模板匹配、数字 OCR、跨帧置信度、只读 market/match 映射和证据保存。
这不是完整 Phase 1，也不是策略、信号、纸面交易或执行层启动许可。

本阶段只验证：
- Polymarket LOL Game Winner 市场发现、orderbook 和行情读取是否稳定。
- 官方赛事 Twitch HLS 纯代码视觉链路是否能在连续两场 Polymarket-backed 比赛中稳定提供 final picks、bans、game clock、gold、objectives。
- 赛程、队伍别名、局数和 Polymarket 市场是否能可靠映射。

连续两场自动化验收与其余 Phase 0 硬门完成前，不启动完整 Data Foundation；完整
数据闭环验收前，禁止新增 strategy / edge / signal / paper trading / wallet /
private key / order 相关实现或配置。

## 工作范围和数据源策略

- 当前主 spike 源：官方赛事 Twitch HLS；运行时使用纯代码模板匹配/OCR，不使用
  LLM。BFX-DK 只证明人工视觉可行性，不计入连续两场自动化验收。
- LoLEsports Frontend API 保留为结构化对照；Cito 保留历史失败/覆盖比较证据，二者
  当前都不是主 live 输入。
- 盘口源：Polymarket public REST/orderbook polling 是 QuoteRecorder v1 baseline；
  WebSocket deferred，作为优化项待 clean network retest，不阻塞延迟型初始闭环。
- 商业备选：PandaScore / GRID / Abios。
- Oracle's Elixir 只用于历史研究，不作为 live 输入。
- 每个 source spike 必须留下原始响应样例、字段清单、延迟记录、限制说明和结论。
- 只有连续两场 Polymarket-backed 比赛都达到 `mappingConfidence >= 0.90`、最终 BP
  精确、正常赛内样本可用率至少 95%、已接受快照零已知错误，才把视觉源记为通过。

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
