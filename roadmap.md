# Polymarket LOL 价值交易系统 — Roadmap

> 版本：v0.2
> 日期：2026-06-15
> 基于：架构框架 v0.2 + v0.3 P0 问题清单
> 当前阶段：Conditional Phase 1 Data Foundation

---

## 0. 路线原则

本项目按“先验证输入源，再建设数据底座，再验证 edge，最后接真钱”的顺序推进。
当前阶段只允许 Data Foundation，不是 full Phase 1。

核心原则：

- Conditional Phase 1 只做数据底座验证，不写策略、不建预测模型。
- Phase 1-3 不接钱包、不引入私钥、不调用真实下单接口。
- Phase 1 唯一交易标的是 `Game N Winner`，不做 Series、Handicap、Total Games。
- 人工/半人工录入只作为 debug / fallback，不作为生产主线。
- 每个阶段必须有可保存、可复盘的产出物；没有证据不算完成。
- 任一硬门失败时，停止进入下一阶段，先重审项目假设。
- 禁止范围：strategy / edge / signal / paper trading / wallet / private key / order。
- DoD：代码类卡不能只靠本地脏树；必须有 PR，无 PR 不验收。文档类卡也应提交 PR；
  若只做文档评论不改 repo，必须在结果中明确说明。
- Secret hygiene：API key / token 不得贴 issue 评论、不得写入 artifact；泄露即轮换。

当前代码库已存在一套 Phase 1 Data Foundation 的本地验证骨架，包括
schema、collectors、resolver、SQLite storage 和 replay smoke test。这些代码只作为
Phase 0/conditional Phase 1 的数据源验证工具，不代表 Phase 0 硬门已经全部通过，
也不代表可以进入 Phase 2 strategy / signal / execution。

---

## 1. Phase 0 — Source Feasibility Spike

**目标：证明自动输入源闭环可行。**

本阶段只回答三个问题：

1. Polymarket 是否能稳定发现 LOL Game Winner 市场并读取 orderbook / WebSocket 行情。
2. 是否至少有一个 LOL 实时数据源能自动提供 final picks、可推算 game clock、gold、objectives。
3. 赛程、队伍别名、比赛局数是否能被稳定映射到 Polymarket 市场。

### 里程碑

| 编号 | 里程碑 | 完成证据 |
|---|---|---|
| P0.1 | Polymarket 行情可用 | 记录至少 1 个 LOL Game Winner 市场的 conditionId、tokenId、best bid/ask、orderbook REST polling 样例；WS 订阅 deferred 到 clean network retest |
| P0.2 | LOL 实时源可用 | 优先验证 LoLEsports Frontend API；至少 1 个候选源实测返回 final picks + derived game clock + gold + objectives，并记录延迟、覆盖联赛、限制 |
| P0.3 | 赛程/映射源可用 | 能从 LoLEsports 或等效源拿到 schedule/event details，并形成 matchId/gameNumber/team alias 映射样例 |
| P0.4 | SourceScore 完成 | 对 LoLEsports Frontend API 优先 spike 源，以及 PandaScore、GRID、Abios、Cito 商业备选源完成打分表 |
| P0.5 | 数据 schema 草案完成 | `markets`、`resolved_markets`、`quotes`、`matches`、`games`、`game_state_snapshots`、`draft_snapshots` 字段草案定稿 |
| P0.6 | Phase 1 输入组合确定 | 明确 1 个主实时源、1 个备选源、1 个赛程/映射辅助源，并记录放弃其他源的原因 |

### Phase 0 硬门

必须同时满足：

- Polymarket public 行情可在无认证下读取 Game Winner market、token、orderbook；REST polling 为 v1 baseline，WS 需 clean network retest 后再升级。
- 至少一个 LOL 实时源自动提供 final picks、可推算 game clock、gold、objectives，字段稳定性足够进入数据底座验证（项目策略为错配/价值交易模型，不追求秒级延迟，Cito 24s 延迟可接受）。
- 当前优先 spike 源为 LoLEsports Frontend API；PandaScore / GRID / Abios 作为商业备选或生产升级源。
- 赛程/映射源能支持 `market -> match -> gameNumber -> team side` 的映射，低置信度市场可被跳过。
- SourceScore 和 schema 草案已记录在案。

### Phase 0 失败处理

- 如果没有可用自动实时源：项目降级为赛前/BP 研究工具，暂停局中交易系统建设。
- 如果 Polymarket LOL Game Winner 行情不可稳定获取：暂停项目，等待市场结构或接口条件变化。
- 如果盘口映射无法达到 `mappingConfidence >= 0.90`：只记录行情，不进入信号层。

---

## 2. Conditional Phase 1 — Data Foundation

**目标：建好数据底座，让系统能稳定“看见”市场与比赛。**

### 进入条件

完整进入 full Phase 1 仍要求 Phase 0 全部硬门通过。当前只允许
`Conditional Phase 1 Data Foundation` 范围内的本地数据底座验证：
market/orderbook REST polling、LoLEsports historical parser、schema/storage、
resolver hard gate 和 replay pipeline。

继续推进前仍必须关闭以下 Phase 0 gates：

- 真实同场 `Polymarket market -> LoLEsports match/game/team side` 映射需在重复
  live 样本中保持稳定且 `mappingConfidence >= 0.90`。CAL-157 已在 G2 vs LYON
  赛中两次达到 `1.0`，但 Game 3 team side 在 365.5 秒内翻转。随后 authenticated
  CITO 重跑时已无 active match，只能确认 identity 与 market-token mapping；live
  game/team-side 交叉验证仍 pending。
- Polymarket Market WebSocket clean network retest，或正式记录 REST polling 为
  v1 baseline。

### 里程碑

| 编号 | 里程碑 | 验收条件 |
|---|---|---|
| P1.1 | Polymarket QuoteRecorder | REST polling baseline 持续写入 `quotes`；WS deferred，clean network retest 通过后再接入 |
| P1.2 | MarketResolver / MatchMapper | `market -> match/game/team side` 映射状态机可运行，低于置信度阈值自动跳过 |
| P1.3 | TeamAliasResolver | 覆盖 LCK、LPL、LEC、国际赛常见队伍别名 |
| P1.4 | LiveGameStateConnector | 选定主源的 game clock、gold、objectives、paused、winner 入库 |
| P1.5 | DraftStateConnector | BP pick/ban/champion、blue/red side、patch 入库 |
| P1.6 | SQLite schema + migration | Phase 1 所需表可重复初始化，字段与 v0.3 验收标准一致 |

### 禁止事项

- 不接 DraftGap 或任何模型作为最终概率。
- 不生成 strategy / edge / signal。
- 不做 paper trading。
- 不接 wallet / private key / order，不做真实下单。

---

## 3. Phase 2 — Strategy Skeleton

**目标：跑通“输入 -> fair probability -> net edge -> signal”的最小闭环。**

### 进入条件

Phase 1 能稳定记录行情、比赛状态、BP 状态，并能完成市场映射。

### 里程碑

| 编号 | 里程碑 | 验收条件 |
|---|---|---|
| P2.1 | TeamStrengthModel | 简版 Elo 输出 `baseProbability` |
| P2.2 | DraftFeatureEngine | DraftGap 或本地 evaluator 只输出 `draftDelta` 特征 |
| P2.3 | FairProbabilityEngine | 使用 logit 融合，输出 bounded `fairProbability` |
| P2.4 | EdgeCapacityCalculator | 基于 orderbook 深度输出 `avgFillPrice`、`executableSizeAtEdge`、`netEdgeAfterSlippage` |
| P2.5 | ExitPlanBuilder | 每个 signal 输出 TP、SL、maxHold、invalidateReasons |
| P2.6 | SignalEngine | 只生成主线赛前/BP 信号，含成本、容量、退出计划 |

### 红线验证

- 信号代码只有一份，回测、纸面交易、未来实盘共用。
- 所有特征严格遵守时序，无未来信息泄漏。
- Edge 必须扣 spread 和 slippage。
- 信号必须输出容量字段。

---

## 4. Phase 3 — Paper Trading Loop

**目标：在真实市场数据上验证主线策略是否有正净 edge。**

### 进入条件

Phase 2 信号链路能稳定产出结构化 signal。

### 里程碑

| 编号 | 里程碑 | 验收条件 |
|---|---|---|
| P3.1 | PaperBroker | 模拟 fill、price、time、position，不触发真实下单 |
| P3.2 | MFE/MAE Tracker | 每笔信号记录最大浮盈、最大浮亏、回归速度、退出质量 |
| P3.3 | PriceConvergenceAnalyzer | 统计信号后市场是否向 fair 方向回归 |
| P3.4 | SignalJournal | 完整记录 signal -> paper fill -> hold -> exit -> outcome |
| P3.5 | 主线净 expectancy 报告 | 按赛区、策略类型、容量、延迟切片统计扣成本后的结果 |

### Phase 3 硬门

- 主线 paper signals 样本数少于 50：无结论，继续记录。
- 扣成本后 expectancy 小于等于 0：不进入非主线策略，重审 FairProbabilityEngine。
- 单联赛表现显著偏离总体：该联赛单独验证，不得用总体结果掩盖。

---

## 5. Phase 4 — Unlock Non-Mainline Strategies

**目标：主线被纸面证明有正净 edge 后，逐个解锁冻结策略。**

### 进入条件

Phase 3 产出正净 expectancy 报告，且样本量、容量、回撤表现满足解锁标准。

### 解锁对象

| 策略 | 额外验证要求 |
|---|---|
| 15min 慢速错价 | 实测 sourceLatencySec 对 MFE 的侵蚀可接受 |
| 后期价值反转 | 经济差失效场景下退出策略有效 |
| 局中资源错估 | 市场过度反应金币、低估资源的证据可量化 |

每个策略必须单独纸面验证至少 30 个观察样本，且扣成本后 expectancy 大于 0。

---

## 6. Phase 5 — Execution Layer

**目标：接入真实交易，但保持可控风险。**

### 进入条件

Phase 3 主线验证通过，或 Phase 4 中某个非主线策略验证通过；真实交易需求被明确批准。

### 里程碑

| 编号 | 里程碑 | 验收条件 |
|---|---|---|
| P5.1 | py-clob-client-v2 集成 | 验证 V2 库可签名、下单、查持仓 |
| P5.2 | RealBroker | 独立包，默认关闭，只能被 ExecutionGate 调用 |
| P5.3 | ExecutionGate | 仓位上限、日亏损上限、熔断、对账可配置 |
| P5.4 | 私钥管理 | 环境变量 + 最小权限钱包，代码库无硬编码密钥 |

### 禁止事项

- 不允许策略层直接调用真实下单。
- 不允许默认启用 RealBroker。
- 不允许在配置文件或代码中保存私钥。

---

## 7. 当前状态

```text
Phase 0: [~] Source Feasibility Spike — 主源定为 Cito（gold/objectives/gameClock/gameState）+ LoLEsports（draft/picks），CAL-59 已验证。CAL-169 两次 active HLE–LYON 样本的 identity 与 market-token mapping PASS（confidence 1.0），但 Game 1 side 再次翻转且 CITO 无 numeric frame，game/team-side PENDING；剩余 gates：authoritative side 与 active numeric-field 稳定性复核、Polymarket WS retest
Phase 1: [~] Conditional Phase 1 Data Foundation — 本地验证骨架已存在，不是 full Phase 1
Phase 2: [ ] Strategy Skeleton — 冻结
Phase 3: [ ] Paper Trading Loop — 未启动
Phase 4: [ ] Unlock Non-Mainline Strategies — 冻结
Phase 5: [ ] Execution Layer — 冻结
```

下一步：按 `tasks.md` 中的当前 P0 blocker 推进：
多场次字段稳定性与 live team-side authority 复核、Polymarket Market WebSocket
retest 或 REST polling baseline 决策，并保持 Phase 2+ 冻结。
