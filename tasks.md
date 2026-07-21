# Polymarket LOL 价值交易系统 — 任务清单

> 版本：v0.2
> 日期：2026-07-21
> 当前阶段：Phase 0 — Source Feasibility Spike
> 阶段目标：验证自动数据输入闭环；只允许只读 source spike、schema 草案和证据整理，不启动 Phase 1 骨架。

---

## 0. 执行规则

- 每个任务必须留下可复查产出：原始响应样例、字段清单、延迟记录、费用/限制说明、结论。
- API key / token 只能走受控 secret 注入，不得贴 issue 评论、不得写入 artifact；
  一旦泄露必须立即轮换。
- API 验证只做读取，不做下单，不接钱包，不接 private key。
- 若某源不可用，记录失败原因，不在代码中绕过约束。
- 当前严格处于 Phase 0。现有 collector/parser/storage/resolver/replay/dashboard 只作为
  历史验证资产；Phase 0 完成前不得继续扩建 Phase 1 代码骨架。
- 禁止范围：strategy / edge / signal / paper trading / wallet / private key / order。
- DoD：代码类卡不能只靠本地脏树；必须有 PR，无 PR 不验收。文档类卡也优先走 PR；
  若只做文档评论不改 repo，必须在结果中明确说明。

---

## 1. Phase 0 优先级

建议执行顺序：

1. `V0` 纯代码视觉提取器 spike：HLS -> ROI -> 英雄模板匹配/OCR -> 跨帧置信度，不使用 LLM。
2. `V1` 连续两场自动验收：只选 Polymarket 有 Game N Winner 盘口的比赛，两场都通过才确认视觉数据源。
3. `F0-06` Polymarket public API 实测：在同两场中复核 market/token mapping 与 CLOB REST/orderbook 稳定性；WebSocket 为非阻塞优化。
4. `F0-00` LoLEsports Frontend API：保留为结构化对照，不再作为当前主 spike 源。
5. `F0-01` PandaScore API 验证：商业备选源，免费层不满足局中数据；至少需 Basic Live。
6. `F0-02` GRID 商务/技术确认：质量最高，但可能成本和门槛最高。
7. `F0-03` Abios trial 验证：备选商业源。
8. `F0-04` Cito 证据归档：不推荐作为 Phase 1 主源或备源，仅保留历史比较证据。
9. `F0-07` 数据 schema 草案与 `F0-08` SourceScore：已完成。
10. `F0-10` Phase 0 Go/No-Go：仅在 V1 与其余硬门关闭后解锁完整 Phase 1 数据闭环。

---

## 2. API 验证任务

### F0-00 — LoLEsports Frontend API Spike

**状态：** [x] 历史样本链路已验证；[ ] live 延迟待验证

**目标：** 将 LoLEsports 前端接口作为 Phase 0 的优先 spike 源，验证其能否低成本替代商业 live data 源进入 Phase 1。

**已验证链路：**

```text
getSchedule -> matchId -> getEventDetails -> gameId -> livestats/window/details
```

**已验证接口：**

- `GET https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US`
- `GET https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US`
- `GET https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={matchId}`
- `GET https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US&id={teamId}`
- `GET https://feed.lolesports.com/livestats/v1/window/{gameId}`
- `GET https://feed.lolesports.com/livestats/v1/window/{gameId}?startingTime={RFC3339}`
- `GET https://feed.lolesports.com/livestats/v1/details/{gameId}?startingTime={RFC3339}`

**已验证字段：**

- schedule / league / team / matchId
- gameNumber / gameId / blue-red side
- final champion picks
- patchVersion
- `rfc460Timestamp`
- `gameState`
- blue/red totalGold
- blue/red kills
- blue/red towers
- blue/red dragons
- blue/red barons
- blue/red inhibitors
- participant level / CS / KDA / health
- details: items / runes / abilities / damage share / wards

**仍需验证：**

- [ ] live match 中最新 frame 的 `sourceLatencySec`
- [ ] live match 中 `window/{gameId}` 的稳定轮询间隔
- [ ] BP 阶段 picks 何时出现
- [ ] bans 是否存在于其他前端接口
- [ ] 暂停 / 重赛 / remake 时 `gameState` 如何变化
- [ ] LCK / LPL / LEC / MSI / Worlds 覆盖是否一致
- [ ] 前端 credential/header 失效时的监控与降级方案

**产出物：**

- `docs/source-spike/lolesports-frontend-notes.md`
- `docs/source-spike/lolesports-event-t1-gen-sample.json`
- `docs/source-spike/lolesports-window-t1-gen-g1-15m-sample.json`
- `docs/source-spike/lolesports-details-t1-gen-g1-15m-sample.json`

**当前完成证据：**

- T1 vs GEN 历史样本可从 matchId 映射到 5 个 gameId。
- Game 1 可按 1/3/5/10/15/20/25/30 分钟拉取局中状态。
- 15 分钟样本包含可交易所需的 gold/objectives/kills/towers/picks。

**当前结论：**

```text
candidate_primary_for_spike = true
candidate_primary_for_production = risky_until_live_validation
```

---

### F0-01 — PandaScore live LoL frame 验证

**状态：** [ ] 商业备选源未验证；仅作为 LoLEsports live validation 失败后的备选路径

**目标：** 确认 PandaScore 是否能作为 Phase 1 的低成本主实时源候选。

**验证字段：**

- `gameClock` 或等价字段
- `paused`
- `finished`
- `winner_id`
- blue/red `gold`
- blue/red `towers`
- blue/red `kills`
- blue/red `drakes`
- blue/red `nashors`
- blue/red `herald`
- blue/red `inhibitors`
- blue/red champions / players
- source timestamp 或 current timestamp

**执行步骤：**

- [ ] 注册或申请 PandaScore credential，并通过受控 secret 注入。
- [ ] 找一场 live 或最近结束的 LoL match，调用 live frame / game frame 相关 endpoint。
- [ ] 保存一份原始 JSON 样例。
- [ ] 记录 observedAt 与 sourceTimestamp，估算 `sourceLatencySec`。
- [ ] 记录覆盖联赛、请求频率限制、免费/付费价格、商业用途限制。

**产出物：**

- `docs/source-spike/pandascore-sample.json`
- `docs/source-spike/pandascore-notes.md`

**完成证据：**

- 明确结论：`usable_as_primary` / `usable_as_backup` / `not_usable`
- 若不可用，必须写清原因：字段缺失、延迟过高、费用不可接受、覆盖联赛不足、权限不足。

---

### F0-02 — GRID official live data 确认

**状态：** [ ]

**目标：** 确认 GRID 是否可作为高质量官方实时源，以及成本是否匹配项目规模。

**必须确认：**

- 是否覆盖 LCK、LPL、LEC、MSI、Worlds。
- 是否提供 BP、game clock、gold、objectives、paused、winner。
- 数据延迟范围。
- API 形式：REST、WebSocket、Push、文件流。
- 接入门槛：合同、KYC、商业用途限制、最低费用。

**执行步骤：**

- [ ] 提交 access / sales / trial 申请。
- [ ] 记录对方回复或公开报价信息。
- [ ] 若可试用，保存字段样例。
- [ ] 与 PandaScore、Abios、Cito 做成本/质量对比。

**产出物：**

- `docs/source-spike/grid-notes.md`

**完成证据：**

- 明确结论：`best_quality_but_expensive` / `candidate_primary` / `not_available`
- 如果价格或权限不可接受，记录为 Phase 1 不采用，但可作为未来升级选项。

---

### F0-03 — Abios trial 验证

**状态：** [ ]

**目标：** 确认 Abios Live Push / Play-by-Play 是否具备交易所需字段深度。

**验证字段：**

- pick/ban
- game clock
- gold
- towers
- dragons
- baron / nashor
- herald
- inhibitors
- paused
- winner / finished

**执行步骤：**

- [ ] 申请 Abios trial。
- [ ] 调用 LoL live / play-by-play / match statistics 相关 endpoint。
- [ ] 保存原始 JSON 样例。
- [ ] 记录延迟、覆盖联赛、请求限制、费用。

**产出物：**

- `docs/source-spike/abios-sample.json`
- `docs/source-spike/abios-notes.md`

**完成证据：**

- 明确结论：`usable_as_primary` / `usable_as_backup` / `not_usable`

---

### F0-04 — Cito / LoLEsportsAPI 验证

**状态：** [x] 历史证据已归档；当前不推荐作为 Phase 1 主源或备源

**目标：** 保存 Cito 已有只读验证证据、限制和失败结论，供源比较使用；不继续将其作为当前主源或备源推进。

**验证 endpoint：**

- `/api/v1/lol/live`
- schedule endpoint
- game stats endpoint
- pick/ban endpoint 或等价字段

**执行步骤：**

- [x] 归档已有响应、字段和限制说明。
- [x] 记录 no-active-match 不能当作 live 成功证据。
- [x] 标记为当前不推荐，不用 fallback 伪造成功。

**产出物：**

- `docs/source-spike/cito-sample.json`
- `docs/source-spike/cito-notes.md`

**完成证据：**

- 明确结论：`not_recommended_for_phase1_primary_or_backup`
- 不得把 key/token 写入 issue 评论或 artifact；只记录无敏感值的调用方式、字段覆盖和稳定性结论。

---

### F0-05 — LoLEsports schedule/event 映射复核

**状态：** [~] CAL-157 authenticated CITO 重跑已完成；无 active match，identity/market-token PASS，game/team-side PENDING

**目标：** 在 F0-00 基础上，专门复核 LoLEsports schedule/event 数据是否足够支撑 Polymarket MarketResolver / MatchMapper / TeamAliasResolver / GameNumberResolver。

**必须验证：**

- schedule 拉取是否稳定。
- event details 是否包含 match、games、teams。
- matchId -> gameId -> gameNumber 映射是否可用。
- 队伍名、简称、别名是否足够与 Polymarket market title 匹配。
- 是否能覆盖 LCK、LPL、LEC、MSI、Worlds。

**执行步骤：**

- [x] 调用 `getSchedule`。
- [x] 调用 `getEventDetails`。
- [x] 保存至少 1 个 BO3/BO5 event 的 source capture JSON。
- [x] 手工比对同一场 Polymarket market title，记录映射难点。

**产出物：**

- `docs/source-spike/lolesports-schedule-sample.json`
- `docs/source-spike/lolesports-event-sample.json`
- `docs/source-spike/lolesports-mapping-notes.md`

**完成证据：**

- 输出一个映射样例：`polymarketTitle -> league -> matchId -> gameNumber -> teamA/teamB`
- 明确 `mappingConfidence` 估算依据。

**当前完成证据：**

- T1 vs GEN 历史 event details 可提供 `matchId -> gameId -> gameNumber -> blue/red side`。
- 当前 replay 中 Polymarket 样例为 KT vs Saigon Warriors，与 LoLEsports 样例不是同一场；
  低置信度 skip 是正确行为，不是映射成功证据。
- CAL-157 在 G2 vs LYON 活跃 BO5 中于 `2026-07-10T09:48:38.926396Z` 和
  `2026-07-10T09:54:44.462731Z` 两次捕获同场映射；match/Game 1-5/team identity
  与 Polymarket Game 1-4 market/token 均稳定，`mappingConfidence=1.0`。
- 同一 live window 内 Game 3 side 从 G2 red / LYON blue 翻转为 G2 blue /
  LYON red，因此完整 team-side hard gate 尚未关闭。
- `2026-07-10T10:50:59.151801Z` authenticated CITO 重跑中，`GET /lol/live`
  返回 HTTP 200 / `no_match` / `count=0`；CITO schedule、LoLEsports event/window
  与 Polymarket Game 1-4 REST 对照确认 identity 和 market-token mapping PASS。
  因已无 active match，CITO Game 3 visual-state 返回 `no_live_match`，game 与
  team-side 交叉验证保持 PENDING，CAL-112 保持 NO-GO。

**仍需验证：**

- [x] 找到真实同一场 Polymarket Game N Winner 市场与 LoLEsports event。
- [x] 记录 `polymarketTitle -> marketSlug -> conditionId -> matchId -> gameNumber -> team side`。
- [x] live 样本 `mappingConfidence >= 0.90`。
- [ ] 确认 authoritative team-side source，并证明重复 live 样本不再翻转。
- [ ] 在下一场 active match 同一采样窗口复核 LoLEsports match/game/picks/side
  与 Polymarket Game Winner token side；Cito 仅保留为历史比较证据。

---

### F0-06 — Polymarket Gamma/Data/CLOB public 实测

**状态：** [~] HTML slug discovery + Gamma slug detail + CLOB REST 已验证；generic search、network path 与 Market WebSocket 仍需处理

**目标：** 验证 Polymarket public 行情是否稳定支持 LOL Game Winner 市场发现、orderbook REST polling 和 WebSocket 读取。

**必须验证：**

- 能按关键词、tag、league 或 slug 发现 LOL Game Winner 市场。
- 能拿到 `conditionId`。
- 能拿到 YES/NO `tokenId`。
- 能读取 orderbook、best bid、best ask、spread、depth。
- WebSocket 必须在 clean network path 复测并保存成功消息或可复现失败证据。
- 能记录 400、429、空市场、暂停市场等异常。

**执行步骤：**

- [x] 调用 Gamma/Data API 搜索 LOL / League of Legends / LCK / LPL / LEC 市场，并记录 generic keyword search 不可靠。
- [x] 识别 Game Winner 与 Series 市场的标题差异。
- [x] 选 1 个 Game Winner 市场，保存 market metadata。
- [x] 调用 CLOB public orderbook endpoint，保存 orderbook 样例。
- [ ] 在 clean network retest 中测试 Market WebSocket 订阅，保存至少 1 条消息样例；失败则保存完整失败证据。
- [ ] 记录接口延迟、限流、错误码、字段不一致情况。

**产出物：**

- `docs/source-spike/polymarket-market-sample.json`
- `docs/source-spike/polymarket-orderbook-sample.json`
- `docs/source-spike/polymarket-ws-sample.json`
- `docs/source-spike/polymarket-notes.md`

**完成证据：**

- 输出 REST 链路样例：`marketSlug -> conditionId -> tokenId -> orderbook -> bestBid/bestAsk`
- WebSocket 完成证据：`tokenId -> WS subscription -> orderbook/trade update`，或保存可复现失败证据。
- 明确 QuoteRecorder v1 基于 public REST polling，WS 只作为后续升级。

**当前完成证据：**

- 已用 `lol-ktc-sgw-2026-06-15-game2` 跑通 `eventSlug -> Gamma event -> Game 2 Winner market -> conditionId -> clobTokenIds -> CLOB orderbook -> bestBid/bestAsk`。
- Game 2 Winner 样例：KT token `bestBid=0.791`、`bestAsk=0.801`；SGW token `bestBid=0.199`、`bestAsk=0.209`。
- Game 1 Winner 可读但盘口单边：KT token `bestBid=0.999`、`bestAsk=null`；SGW token `bestBid=null`、`bestAsk=0.001`。
- 2026-07-03 复测确认 Polymarket 服务本身可达；`SSL_ERROR_SYSCALL` / browser `ERR_CONNECTION_CLOSED` 更像当前 WSL 代理、直连或 TLS 协商路径不稳定，不是 Polymarket LOL 页面整体不可用。
- 当前代理通常为 `HTTP_PROXY/HTTPS_PROXY=http://192.168.240.1:7897`；默认 curl 成功过，`curl --http1.1` 也失败过，直连失败，不能把 `--http1.1` 当作稳定万能 workaround。
- Gamma basic endpoint 可用，但 generic keyword search 不可靠：`league of legends`、`lol`、`t1` 可返回 `HTTP 200` 但结果为 Kraken IPO、Macron、UK election 等无关市场；`msi` 多次 TLS 失败。
- 推荐 market discovery fallback：`Polymarket LOL page HTML -> event slug -> Gamma /events/slug/{slug} -> Game [1-5] Winner filter -> CLOB /book`。
- 页面 HTML 暴露 4 个 LOL event slug：`lol-ly-fur-2026-07-03`、`lol-blg-t1-2026-07-04`、`lol-tsw-tes-2026-07-04`、`lol-hle1-g2-2026-07-05`。
- Gamma slug detail 已确认当前样例存在 `Game N Winner`：LYON vs FURIA、BLG vs T1、Team Secret Whales vs Top Esports、Hanwha Life Esports vs G2 均有 Game 1/2/3/4 Winner。
- 未发现 `Game 5 Winner`；当前样例中 Game 5 只看到 dragon / inhibitor / kill 等 props，不纳入 Phase 1 `Game N Winner` 主范围。
- CLOB `/book` 已验证 `lol-blg-t1-2026-07-04-game1`：conditionId `0x52671a734b1872bab38ddaf5113a4716fb81b5bfb9e794475fadbea0fbacf0cf`；Bilibili token `bids=30`、`asks=31`、`bestBid=0.47`、`bestAsk=0.48`。
- REST polling 已证明可采样，但不能据此跳过 WebSocket Phase 0 复测，也不得启动 Phase 1 QuoteRecorder 实现。

---

## 3. 架构落地任务

### F0-07 — Phase 1 数据 schema 草案

**状态：** [x] 已完成；`docs/schema-phase1.md` 已存在

**目标：** 定义 Phase 1 必需表结构，保证行情、比赛、BP、局中状态、映射结果可统一落库。

**必须覆盖表：**

- `markets`
- `resolved_markets`
- `quotes`
- `matches`
- `games`
- `game_state_snapshots`
- `draft_snapshots`

**执行步骤：**

- [ ] 从主架构文档 13.4.1 至 13.4.3 提取字段。
- [ ] 为每个表定义主键、外键、时间字段、source 字段、confidence 字段。
- [ ] 明确哪些字段来自 Polymarket，哪些来自 LOL 数据源，哪些来自 resolver。
- [ ] 记录字段类型和 nullable 规则。

**产出物：**

- `docs/schema-phase1.md`

**完成证据：**

- `markets`、`resolved_markets`、`quotes`、`matches`、`games`、
  `game_state_snapshots`、`draft_snapshots` 字段草案已记录。
- 本地 SQLite storage 已能初始化这些表并支持 replay smoke test。
- 该 schema 只用于数据底座，不允许据此启动 strategy / edge / signal / paper trading。

---

### F0-08 — SourceScore 打分体系

**状态：** [x] 已完成；`docs/source-score.md` 已存在，live latency 分数仍带 pending risk

**目标：** 用统一标准选择 Phase 1 主实时源和备选源，避免凭直觉选型。

**评分维度：**

| 维度 | 权重 | 说明 |
|---|---:|---|
| officialness | 20 | 官方程度、数据授权稳定性 |
| latency | 20 | sourceTimestamp 到 observedAt 的延迟 |
| fieldCoverage | 25 | final picks / bans、clock 或 derived clock、gold、objectives、paused、winner 覆盖程度 |
| reliability | 15 | 字段稳定、服务稳定、文档清晰 |
| leagueCoverage | 10 | LCK、LPL、LEC、国际赛覆盖 |
| costFit | 10 | 成本是否匹配 $2k-$20k 资金规模 |

**执行步骤：**

- [x] 为 LoLEsports 主 spike、PandaScore 商业备选、GRID 未来升级、Oracle's Elixir 历史用途及 Cito/非官方源限制打分。
- [x] 每个维度写一句证据，不只填数字。
- [x] 输出主 spike、商业备选、未来升级、历史用途和不推荐源列表。

**产出物：**

- `docs/source-score.md`

**完成证据：**

- Phase 1 主输入源组合有明确选择理由。
- 弃用源有明确放弃原因。

---

### F0-09 — 历史验证资产冻结

**状态：** [x] 已冻结；只允许作为 Phase 0 验证资产使用

**目标：** 保留现有 parser、collector、resolver、storage、replay 和 dashboard 用于只读
Phase 0 证据复核，不新增 Phase 1 模块或能力。

**边界说明：**

- 这些资产已在 Phase 0 gate 关闭前存在，现冻结为数据源验证工具。
- 不得在该骨架中新增 strategy、edge、signal、fair probability、paper trading、
  broker、wallet、private key 或真实下单逻辑。

**计划目录：**

```text
src/pm_lol/
  collectors/
  resolvers/
  sources/
  storage.py
  replay_pipeline.py
tests/
docs/
```

**执行步骤：**

- [ ] 创建 `pyproject.toml`。
- [ ] 创建 `src/pm_lol/` 包结构。
- [ ] 创建 `tests/`。
- [ ] 添加基础 lint/test 命令。
- [ ] 不引入 RealBroker、不引入私钥配置。

**产出物：**

- Python 项目骨架。

**完成证据：**

- 能运行基础测试命令。
- 包结构与 Phase 1 模块边界一致。
- 当前代码未发现 strategy / edge / signal / paper trading / broker / execution / wallet 实现。

---

### F0-10 — Phase 0 Go/No-Go

**状态：** [ ] NO-GO；Phase 0 硬门尚未全部关闭

**目标：** 基于实测结果判断自动输入闭环是否成立；通过前不讨论 Phase 1 实现。

**输入：**

- F0-01 PandaScore 结论。
- F0-02 GRID 结论。
- F0-03 Abios 结论。
- F0-04 Cito 结论。
- F0-05 LoLEsports schedule/event 结论。
- F0-06 Polymarket public 结论。
- F0-08 SourceScore。

**决策格式：**

```text
Polymarket market source:
Live game primary source:
Live game backup source:
Schedule/mapping source:
Rejected sources:
Main risks:
Phase 0 Go/No-Go decision:
```

**产出物：**

- `docs/decision-log.md`

**完成证据：**

- 明确当前 `NO-GO`：只允许 Phase 0 只读验证。
- 明确 remaining gates：LoLEsports active-match 字段/延迟、真实重复映射、Polymarket REST/WS 稳定性。
- 明确 no-go triggers：自动 live source 不可用、Polymarket 行情不可稳定获取、
  真实映射无法达到 `mappingConfidence >= 0.90`。

---

## 4. Phase 0 完成条件

```text
[~] Polymarket public 行情实测可用：HTML slug discovery + Gamma slug detail + Game Winner tokenId + CLOB orderbook REST 已验证；generic search、网络路径和 WS 仍待复测
[~] 至少一个 LOL 实时源实测可用：官方赛事 Twitch HLS 已通过人工视觉可行性验证；纯代码模板/OCR 提取与连续两场自动化 V1 验收未完成
[~] 赛程/映射源实测可用：CAL-157 authenticated CITO 重跑为 no-active-match/near-live；identity 与 market-token PASS，game/team-side PENDING，稳定性 gate 未关闭
[x] SourceScore 完成：候选源有证据打分，live latency 风险仍 pending
[ ] Phase 1 未启动：Phase 0 全部硬门关闭前保持冻结
[x] Phase 1 schema 草案完成：核心 connector 输出可落库
[x] go/no-go 决策写入 `docs/decision-log.md`：`PHASE_0_NO_GO` with open gates
```

当前 P0 blockers：

- [ ] Live mapping stability：同一场 Polymarket Game N Winner 与 LoLEsports
  event/game/team identity 已达到 `mappingConfidence=1.0`；仍需确认 authoritative
  team-side source，并在重复 live 样本中保持稳定。
- [ ] Automated visual-source stability：完成 V0 纯代码提取器，并在连续两场 Polymarket-backed 比赛中验证 final picks、bans、clock、gold、objectives、confidence、observedAt 和端到端 freshness。
- [ ] Polymarket REST/orderbook stability：重复采样并记录空盘口、关闭市场、429 和网络失败。
- [ ] Polymarket Market WebSocket retest（非阻塞优化）：成功保存订阅消息；失败保存可复现证据。初始延迟型闭环可使用已验证稳定的 REST polling。

---

## 5. 后续阶段占位

Phase 1 之后的任务只保留阶段入口。Phase 0 gates 关闭前，Phase 1+ 全部冻结。

- [ ] **F1** Data Foundation：QuoteRecorder、MarketResolver、LiveGameStateConnector、DraftStateConnector、SQLite schema。
- [ ] **F2** Strategy Skeleton：Elo、DraftFeature、FairProbability、EdgeCapacity、ExitPlan、SignalEngine。
- [ ] **F3** Paper Trading Loop：PaperBroker、MFE/MAE、PriceConvergence、SignalJournal、expectancy 报告。
- [ ] **F4** Non-Mainline Unlock：15min、后期反转、资源错估逐个纸面验证。
- [ ] **F5** Execution Layer：py-clob-client-v2、RealBroker、ExecutionGate、私钥管理。

---

## 6. Approved execution queue — 2026-07-21

### V0 — Pure-code visual extractor spike (current)

- [ ] Add versioned broadcast-layout configuration and gameplay/replay screen
  classification.
- [ ] Download and version the Riot Data Dragon champion template set.
- [ ] Extract ten final picks and ten bans with template matching and confidence.
- [ ] OCR clock, gold, kills and tower counters from fixed ROIs.
- [ ] Extract dragon and Baron state; extract inhibitor state when the event is
  observable.
- [ ] Require cross-frame agreement and emit `unknown`/skip below confidence
  thresholds.
- [ ] Emit normalized read-only snapshots plus raw evidence; no model, signal or
  execution code.

### V1 — Two-consecutive-match acceptance gate

- [ ] Select two consecutive matches that both have active Polymarket Game N
  Winner markets and accessible official/event broadcasts.
- [ ] Run the extractor continuously through both matches without manual field
  entry.
- [ ] Require `mappingConfidence >= 0.90`, stable game/team/token identity,
  exact final BP, >=95% usable normal-game samples and zero incorrect accepted
  snapshots.
- [ ] Reconcile each run against postgame ground truth and publish raw frames,
  normalized snapshots, confidence/freshness metrics, interruptions and a final
  pass/fail report.
- [ ] Only when both consecutive matches pass, record the visual source as
  qualified and perform the Phase 0 Go/No-Go update.

The BFX-DK evidence is the feasibility baseline and does not count as an
automated V1 pass.

### F1 — Complete read-only data loop (locked until V1 passes)

- [ ] Polymarket LOL discovery -> Game Winner filtering -> token/orderbook REST
  capture.
- [ ] Market/match/game/team mapping -> broadcast resolver -> frame sampler ->
  extractor -> normalized snapshot storage.
- [ ] Health/freshness/confidence metrics, idempotent restart, replay and
  postgame reconciliation.
- [ ] Full-match unattended acceptance run with no strategy or signal output.

### F2 — Strategy engineering (locked until F1 passes)

- [ ] Team-strength prior and chronological training/evaluation data.
- [ ] Time-varying draft power curve and conditional live-state interactions.
- [ ] Executable price, spread/slippage and net-value calculations.
- [ ] Historical evaluation, calibration and paper-only signal journal.
- [ ] No wallet, private key or real order path.

### UI — Read-only monitoring frontend (locked until F1 contracts and F2 outputs are stable)

- [ ] Market/match/game identity and current BP/live-state panels.
- [ ] Source health, freshness, field confidence and skip reasons.
- [ ] Polymarket orderbook plus fair probability/net-value comparison.
- [ ] Timeline, replay and audit views; no duplicate calculation logic and no
  execution controls.
