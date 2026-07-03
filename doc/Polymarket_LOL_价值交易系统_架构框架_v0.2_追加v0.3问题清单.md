# Polymarket LOL 价值交易系统 — 架构框架文档

> 版本:v0.2 + v0.3 P0 追加
> 状态:方向性框架已定;当前执行以 v0.3 P0 硬门为准
> 相对 v0.1/v0.2 的主要变更:① 改名为「价值交易」并引入交易质量指标 ② 策略「保留但强约束」而非简单删除/降级 ③ v0.3 将人工录入降为 debug / fallback,自动实时源验证前置为 Phase 0 硬门 ④ 仅做 Game Winner,Series 用概率树后置 ⑤ 修正 Polymarket 技术选型为 V2 ⑥ 信号必须输出容量字段
> 本文档目的:固化已确认事实、方向性决策与 v0.3 P0 验证计划。若 v0.2 与 v0.3 冲突,以 v0.3 P0 追加为准。

---

## 当前有效决策(v0.3 优先级说明)

v0.2 中“Phase 1 接受人工/半人工录入实时状态”的判断已被 v0.3 修正:

```text
人工/半人工录入 = debug / fallback
生产主线 = 必须找到可自动抓取的 final picks + 可推算 game clock + gold/objectives 输入源
```

因此当前项目不直接进入策略开发。下一步是 Phase 0 Source Feasibility Spike:

1. 验证 Polymarket Game Winner 市场发现、orderbook、WebSocket 行情。
2. 验证至少一个 LOL 实时数据源能自动提供 final picks、可推算 game clock、gold、objectives。
3. 验证赛程/映射源能支持 `market -> match -> gameNumber -> team side`。
4. 完成 SourceScore、Phase 1 schema 草案和 go/no-go 决策。

Phase 0 未通过前,不得启动策略、纸面交易或实盘执行层。

## 0. 命名与本质(v0.2 修正)

本项目**不是严格套利**(无锁定无风险价差)。本质是**概率优势交易 / 价值交易(Value Trading / Mispricing)**:

```
判断:自有公允胜率 > Polymarket 当前隐含胜率,则建仓
```

因此必然存在回撤、误判、流动性损耗。这个定性直接影响评估口径(见第 6 节红线 R6):不能只看「最终赢没赢」,否则会把「判断对但退出错」误判为坏信号,从而错误地砍掉实际有 edge 的策略。

---

## 1. 项目定位

在 Polymarket 的 LOL 比赛市场上,通过自有概率估计与市场隐含概率的差值进行价值交易。

可参与盘口(已通过实盘页面侦察确认):

- **Phase 1 唯一目标:Game 单局胜负盘**(Game N Winner)
- **Phase 2 扩展:Series 比分盘**(Moneyline / Handicap / Total Games),需独立的概率树模型
- 其余 props(小龙/男爵/五杀等)经侦察确认流动性为零或极薄,不纳入

> 范围说明:用户最初设想 Game 盘为主力、Series 盘为次要并行。评审后收缩为 Phase 1 仅 Game Winner。理由见第 5 节。此为需用户最终确认的范围收缩。

---

## 2. 已确认的关键约束(架构地基)

经实地侦察与检索确认的事实,直接决定架构方向。

| # | 约束 | 对架构的影响 |
|---|------|-------------|
| C1 | Polymarket 无官方实时比赛数据喂价,价格仅由人工交易者驱动 | 价格滞后 = 人没反应过来,而非做市商犯傻;用户优势是「市场对 LOL 局势理解慢」 |
| C2 | 用户无低延迟数据源(决策:暂不付费),看直播有 1–2 分钟延迟 | 结构性放弃纯速度套利;但「市场慢」的窗口可能持续数分钟 → 慢速错价仍可能有 edge(见第 3 节) |
| C3 | 次级联赛流动性薄(实测单局盘深度约 $7.4K,spread ≈ 1¢) | 流动性必须作为信号的一等输出(容量字段),不能事后判断 |
| C4 | 资金量级:总 $2k–20k,单场 $200–1k | 仅 LCK/LPL/LEC 正赛及国际赛主盘流动性够用 |
| C5 | Oracle's Elixir 网页全站对自动抓取返回 403 | 不能实时调用其 EGR 工具;改用其 S3 可下载数据集 + 公开系数自建等价模型 |
| C6 | LPL 为腾讯独立数据体系,Oracle's Elixir 对 LPL 数据完整性历史上时有缺失 | LPL 上模型表现须单独验证 |
| C7 | **官方 `py-clob-client` 已于 2026-05-11 归档并标注「不再可用」,须用 `py-clob-client-v2`** | Phase 4 技术选型直接锁定 V2,旧库会导致集成报废 |
| C8 | Polymarket Gamma/Data API 公开无认证;CLOB 有公共行情端点 + 认证交易端点 | Phase 1 行情读取无需钱包;Phase 4 才接钱包/签名 |

---

## 3. 核心策略逻辑(v0.2:保留但强约束)

唯一 alpha 来源:**自有公允概率比市场隐含概率更准**。净收益 =(自有概率 − 市场隐含概率)扣除交易成本后的部分。

### 策略族与状态

| 策略 | 性质 | v0.2 状态 |
|------|------|-----------|
| 赛前定价偏差 | 无速度竞赛,最稳 | **主线,默认启用** |
| BP / 阵容偏差 | BP 后市场反应不足 | **主线,默认启用** |
| 15min 慢速错价(原「瞬时套利」) | 非速度型;15–18 分钟市场仍错误定价 | **保留,默认禁用**,见下方约束 |
| 后期价值反转(原「速度反转」) | 经济差已失效但市场仍按经济差定价 | **保留,默认禁用**,见下方约束 |
| 局中资源错估 | 市场过度反应金币、低估资源 | **保留,默认禁用**,见下方约束 |

### 关于「保留但强约束」(本项目与评审意见的分歧处理)

评审建议将 15min/后期策略由「删除」改为「降级保留」,理由正确:用户优势是市场理解慢,慢窗口可达数分钟而非数秒,不应因「没有速度」就否定这两类。

但本项目处境特殊(中等资金、无低延迟数据、单人开发),「降级」的措辞会诱导精力回流、铺开过多半成品策略。因此采纳「保留」但施加强约束:

```
这三个非主线策略默认禁用。
解锁条件:主线(赛前+BP)经纸面交易阶段证明扣成本后正净 edge 后,
          方可逐个解锁,且每个解锁前必须在纸面阶段单独验证
          「直播 1–2 分钟延迟实际吃掉多少利润」。
```

即:不是「次要但可做」,而是「冻结,达标后逐个解冻并单独证伪延迟损耗」。这是「保留可能性」与「集中精力」之间针对本项目约束的平衡。

已知可用的局中公开系数(EGR):15 分钟时每 ~320 金 ≈ 4.0pp 胜率,每条小龙 ≈ 7.5pp 胜率(小龙胜率价值约为金币两倍)。市场散户倾向过度反应屏幕最大数字「金币差」、低估「资源差」——此偏差不依赖速度,是局中策略的理论 edge 来源。

---

## 4. 三个外部信息源的性质与边界(升级为红线)

不是「多个模型结合」,而是「多组输入特征喂给一个自建融合层」:

- **DraftGap**:阵容特征源,**不是最终胜率裁判**。只懂英雄、不懂队伍。开源,可离线复现。
- **Oracle's Elixir**:数据集 + 描述性面板,不是预测引擎。提供 S3 可下载历史数据(训练/回测用)+ 公开 EGR 系数。其下载页提供 LCS/LEC/LCK/LPL 等联赛数据文件。
- **实时游戏状态**:三源均不提供稳定实时流。这是架构最大缺口(见第 5 节 Phase 1 处理)。
- **自建融合层 = 唯一 alpha 所在**:

```
FairWinrate = TeamStrengthBase            (队伍/选手实力,Elo 基线)
            + DraftAdjustment             (DraftGap 特征,有界修正)
            + SideAdjustment              (蓝/红方)
            + Patch/MetaAdjustment        (版本/Meta 衰减)
            [ + InGameAdjustment ]        (局中:EGR 系数,仅解锁后)
```

DraftGap 仅为 `draft_edge_feature`,永不作 `final_probability`。此边界为架构红线 R4。

---

## 5. 实时数据缺口与 MVP 处理(v0.2 新增)

架构最大难点不是三个已知源,而是**实时游戏状态从哪来**:当前时间、实时经济差、小龙/塔/大龙、装备、BP、是否暂停、第几局、蓝红方。Oracle's Elixir 的可下载 CSV 适合历史训练/回测,**不等于稳定实时数据源**。

**v0.2 原决策:接受人工/半人工录入实时状态。**

**v0.3 修正:人工/半人工录入只能作为 debug / fallback,不能作为生产主线。Phase 1 进入条件改为:Phase 0 已验证至少一个自动实时 LOL 输入源可用。**

```
Phase 1 MVP(v0.2 原设想,已被 v0.3 收紧):
  Polymarket 自动抓价格(无钱包,公开端点)
  LOL 状态 人工/半人工录入(赛前 / BP / 15min 关键点)
  系统计算 edge
  控制台 / TG 推送信号
```

v0.2 的理由是先以最低成本证明「Polymarket 价格是否真的滞后、自有判断是否真有 edge」,不让项目第一版卡死在实时数据采集工程上。v0.3 复核后认为:若没有自动 final picks、可推算 game clock、gold/objectives 输入源,系统只能成为赛前研究工具,无法形成稳定局中价值交易闭环。因此全自动输入源验证前置到 Phase 0。

**Game 盘 vs Series 盘必须分离建模:**

- Game 盘模型:当前这一局谁赢
- Series 盘模型:当前比分 + 当前局胜率 + 后续每局胜率 → 概率树(BO3:P(2-0)/P(2-1)/P(1-2)/P(0-2))

直接拿单局 edge 映射到 series handicap 是错误的。故 **Phase 1 只做 Game Winner,Series 树留 Phase 2**。

---

## 6. 关键架构红线

| # | 红线 | 说明 |
|---|------|------|
| R1 | 信号引擎单一来源 | 回测器与实盘执行器调用完全同一份信号代码,差异仅在「历史重放 vs 实时流」「模拟 vs 真实下单」 |
| R2 | 回测/实盘同 schema | 否则「回测好」与「实盘好」不可比 |
| R3 | 严格时序无泄漏 | 预测特征严格只来自该场开始前;回测须 walk-forward,非一次性 train/test split。所有 LOL 预测项目最常见致命伤 |
| R4 | DraftGap 仅为特征 | 永不作最终胜率;融合层公式见第 4 节 |
| R5 | 信号必须扣交易成本 | edge 判定基于净利(扣 spread + 滑点),非毛利 |
| R6 | 交易质量评估口径 | 除最终输赢外,必须记录:是否发生价格回归、最大浮盈 MFE、最大浮亏 MAE、回归速度、退出策略质量。防止「判断对/退出错」被误判为坏信号 |
| R7 | 信号必须输出容量 | 见第 7 节信号 schema;edge 再大若只能吃 $80 则无意义 |
| R8 | 风险递增分阶段 | 零金钱风险模块先行,真金模块最后 |

---

## 7. 信号输出 Schema(v0.2 新增,落实 R5/R6/R7)

每个信号为结构化对象,至少包含:

```
fairProbability      自有公允概率
marketPrice          当前市场隐含价
grossEdge            毛 edge = fair - market
spreadCost           点差成本(实测口径)
slippageCost         滑点成本(按深度估)
netEdge              净 edge(grossEdge - 成本)
maxFillSize          当前订单簿可成交上限
recommendedSize      结合 C4 资金约束的建议下注额
capacityScore        容量评分(netEdge 与 maxFillSize 的综合)
```

回测若不计容量与成本,会严重高估收益。此 schema 同时服务回测与实盘(R1/R2)。

---

## 8. 分层架构

```
外部数据源
  ├─ Polymarket (CLOB / Gamma / Data API)   行情、订单簿、赛程
  ├─ Oracle's Elixir (S3 可下载数据集)       历史数据(训练/回测)
  ├─ DraftGap (开源模型)                     阵容特征
  ├─ LoLEsports Frontend API                  schedule、event、match/game metadata、final picks、经济、资源、赛果
  ├─ 商业 LOL 实时数据源(PandaScore/GRID/Abios/Cito)
  │                                           official/paid backup：BP、game clock、经济、资源、暂停、赛果
  └─ 人工/半人工录入                          debug / fallback,不作为生产主线
        │
        ▼
采集层 Collectors  (只标准化落库,零判断)
  · Polymarket 行情轮询 / 赛程发现与流动性过滤
  · ScheduleCollector / MatchMapper 输入
  · LiveGameStateConnector / DraftStateConnector
  · ManualStateInput(debug / fallback)
        │
        ▼
存储层 Storage  (回测/实盘共用 schema — R2)
  · markets / quotes / signals / positions / fills
  · 交易质量字段:MFE / MAE / 回归速度 (R6)
        │
        ▼
策略与信号层 Strategy  ← 项目核心,alpha 所在
  · 自建融合层(第 4 节公式)→ FairWinrate
  · 信号引擎:净 edge + 容量(第 7 节 schema)
  · 红线 R1:回测/实盘共用同一份信号代码
        │
        ├──────────────┐
        ▼              ▼
回测/纸面交易层      执行与风控层(最后建,最高风险)
  · walk-forward 回测  · py-clob-client-v2(C7)
  · 实时模拟下单       · 钱包/签名/滑点/部分成交
  · MFE/MAE/回归速度   · 仓位上限/熔断/对账
        │              │
        ▼              ▼
调度与监控 Orchestration
  · 赛程驱动定时任务 · 健康检查 · 告警 · 结构化日志
```

---

## 9. 技术选型方向(v0.2 更新)

| 项 | 决策 | 理由 |
|----|------|------|
| 语言/栈 | 纯 Python,无前后端分离 | 现阶段无前端;SDK/数据/建模生态最顺 |
| 运行环境 | 本地优先,代码可平移 VPS | 路径/密钥/间隔走配置,不写死 |
| Polymarket 行情 | Gamma/Data API + CLOB 公共端点(无钱包) | C8;Phase 1 只读 |
| Polymarket 交易 | **`py-clob-client-v2`**(非旧版) | C7,旧版已归档不可用 |
| 存储 | 起步 SQLite/Parquet,可升级 PostgreSQL | 中等资金单机起步够用 |
| 调度 | 起步 cron / APScheduler | 赛程驱动,规模小 |
| 私钥管理 | 环境变量 + 最小权限钱包,绝不硬编码 | 安全底线 |

---

## 10. 分阶段路线图(MVP 优先级)

```
0. Source Feasibility Spike:验证 Polymarket 行情、自动 LOL 实时源、赛程/映射源
1. Polymarket Game Winner 行情采集(自动,无钱包)
2. 自动采集 final picks / derived game clock / gold / objectives;人工录入仅保留 debug / fallback
3. 自建 FairWinrate 简单模型(Elo 基线 + DraftGap 特征)
4. edge 信号(含容量/成本)+ paper trade
5. 复盘 MFE / MAE / 回归速度,验证主线净 edge
6. 达标后:逐个解锁非主线策略 → 更高质量实时数据源 → 实盘执行
```

| 阶段 | 金钱风险 | 实盘留用 |
|------|---------|---------|
| 0(Source Feasibility Spike) | 零 | 文档、样例、schema、选型结论留用 |
| 1–5(采集/模型/纸面/复盘) | 零 | 全部留用(骨架+核心) |
| 6(解锁/自动化/实盘) | 真金 | — |

Phase 0 是 go/no-go 阶段,不写策略。Phase 1-5 的每行代码才是未来实盘骨架。仅把「真钱赌未验证策略」后移至主线被纸面证明有正净 edge 之后。

---

## 11. 待后续细化(本轮不展开)

1. **需要使用的具体工具清单**:各层具体库、Polymarket V2 接口封装、DraftGap 复现细节、EGR 等价模型形式、自动实时源 connector 与人工 fallback 工具形态。
2. **Baseline Predictor 集成**:
   - 项目 `farrelo25/lol-esports-predictor`(Hugging Face):Oracle's Elixir 2014–2026 + 双 ELO + XGBoost + Polymarket edge 接口。
   - 定位:**参考实现 + baseline,不作交易核心,不直接信其跑实盘**。
   - 集成前必审:① 时序泄漏 / 是否 walk-forward;② 是否扣 spread/滑点(几乎肯定未做,需补);③ LCK/LPL/LEC 分赛区切片验证(尤其 LPL 数据完整性);④ 是否对 patch/meta 衰减;⑤ 是否支持 BP / 局中状态。
   - 价值定位:它若仅为赛前强弱模型,最多覆盖约 30% 问题。剩余 alpha(BP 后修正、15min/EGR、25/30min scaling、超后期经济失效)仍需自建。提供已搭通的双 ELO+XGBoost+Oracle 管线参照系,使精力聚焦于其缺失部分。
3. 各策略量化触发阈值(框架未定前不定)。
4. 风控具体参数(单场/总敞口上限、熔断线)。
5. Series 概率树具体形式(Phase 2)。

---

## 12. 一句话总结

靠概率估计质量(而非速度)取胜的、赛程驱动的分层价值交易系统;唯一 alpha 在自建融合层;唯一不可省的是严格无泄漏的时序回测 + 交易质量评估口径;主线为赛前/BP 偏差,其余策略冻结至主线证实后逐个解锁;Phase 0 先验证自动输入源闭环,Phase 1 仅做 Game Winner;人工录入只作 debug / fallback;Predictor 作 baseline 加速验证而非替代验证。


---

## 13. v0.3 P0 问题清单与验证计划（追加，不修改前文）

> 追加原则：本节原为追加在 v0.2 文档之后的 P0 问题清单。当前执行上,v0.3 P0 约束优先于 v0.2 中较宽松的 MVP 设想。
>
> 核心修正：人工/半人工录入不能作为生产主线，只能保留为 debug / fallback。主线必须找到可自动抓取的输入源，并把 MarketResolver → LiveGameState → DraftState → FairProbability → EdgeCapacity → PaperTrade 串成闭环。

### 13.1 当前必须解决的 P0 问题

| 编号 | 问题 | 风险 | 解决模块 | 初步处理方向 |
|---|---|---|---|---|
| P0-1 | 缺少自动实时 LOL 输入源 | 只能做赛前工具，做不了稳定局中价值交易 | `LiveGameStateConnector` | 优先验证 LoLEsports Frontend API 的字段、延迟、覆盖联赛；GRID / PandaScore / Abios / Cito 作为商业备选/升级源 |
| P0-2 | Polymarket 盘口与真实比赛/局数映射不稳定 | Game/Series 混淆、Game 1/2/3 混淆、队伍方向错误 | `MarketResolver` / `MatchMapper` | 建立 market_slug/condition_id/token_id 与 matchId/gameId/gameNumber 的映射状态机 |
| P0-3 | 缺少 Polymarket 历史盘口记录 | 无法验证市场是否真的慢、容量是否够、MFE/MAE 是否真实 | `QuoteRecorder` | 从 Phase 0 开始记录 orderbook / bid / ask / spread / depth / last trade |
| P0-4 | BP/Draft 输入未自动化 | DraftGap 无法稳定进入系统，BP edge 无法规模化 | `DraftStateConnector` | 优先用 LoLEsports Frontend API 获取最终 picks；bans 与 BP 顺序后续单独验证；DraftGap 只做本地阵容特征计算 |
| P0-5 | FairWinrate 公式不能直接概率加法 | 胜率容易加爆，强队场景过度自信 | `FairProbabilityEngine` | 改为 logit 融合：base_prob → logit → 加 delta → sigmoid |
| P0-6 | Edge/容量不能只看 mid price | 回测高估可成交收益 | `EdgeCapacityCalculator` | 按订单簿深度计算 maxBuyPrice / avgFill / executableSizeAtEdge |
| P0-7 | 缺少退出策略 | 系统只能预测，不能交易；判断对但退出错无法归因 | `ExitPlanBuilder` | 每个信号必须输出 takeProfit / stopLoss / maxHold / invalidateReasons |
| P0-8 | 主线成功/非主线解锁标准模糊 | 15min/后期策略过早扩张 | `UnlockCriteriaEvaluator` | 用样本数、净 expectancy、MFE/MAE、回归率、容量、分联赛表现定义解锁条件 |
| P0-9 | Baseline Predictor 可能过早分散注意力 | 模型复杂化，但交易闭环没跑通 | `BaselineAdapter`（后置） | 先跑通简版 Elo + Draft 修正闭环，再接入 baseline 对照 |
| P0-10 | 实盘执行层必须隔离 | 策略层误调用真实下单风险 | `PaperBroker` / `RealBroker` / `ExecutionGate` | Phase 1-3 不接私钥；RealBroker 独立包且默认关闭 |

---

### 13.2 自动输入源验证矩阵

| 来源 | 用途 | 当前验证状态 | 初步结论 | 下一步 |
|---|---|---|---|---|
| Polymarket Gamma / Data / CLOB Public | 市场发现、价格、订单簿、盘口记录 | 已通过官方文档验证公开行情可无认证读取；CLOB 市场 WebSocket 可订阅 orderbook/trade | 可作为 Phase 0/1 盘口主源 | 实测发现 LOL Game Winner 市场、订阅 token orderbook、落库 quotes |
| Polymarket CLOB V2 | 未来真实交易执行 | 已验证旧 `py-clob-client` 归档且不再可用；生产需 V2 | 执行层必须按 V2 设计 | Phase 4 才接，Phase 1-3 不引入私钥 |
| Riot / GRID Official LoL Esports Data | 最优实时游戏状态、BP、赛程、目标资源 | 已验证 Riot 官方将 LoL Esports 数据通过 GRID 分发；包含 live in-game info、fixture data、gold/objectives 等 | 最优但可能需要商业申请/权限 | 申请/联系 GRID，确认费用、可用联赛、字段、延迟、API 形式 |
| GRID League of Legends Data Portal | 官方 LoL 数据门户 | 已验证页面显示 real-time game data / match history / current game state；Betting/Fantasy 场景为付费 | 可作为高质量付费源候选 | 申请 access，确认是否可覆盖 LCK/LPL/LEC/国际赛 |
| PandaScore LoL Frames | 实时游戏帧、队伍统计、玩家统计 | 已验证文档包含 current_timestamp、paused、finished、winner_id、blue/red gold/towers/kills/drakes/nashors/herald/inhibitors/champion 等字段 | 商业 API 备选；免费层不足以支撑局中交易，至少需 Basic Live/Pro Live | 申请 API key，跑 1 场 live match 字段验证 |
| Abios | 赛程、历史、Live Push、Play-by-Play | 已验证支持 REST & Push APIs、Live Push API Channels、Live Play-by-Play Statistics、14 天试用 | 候选源，字段深度需进一步确认 | 申请 trial，确认是否有 LoL gold/objectives/pickban/game clock |
| Cito / LoLEsportsAPI | 自助式 LoL live/schedule/stats/webhooks | 已验证提供 live matches/schedules、pick/ban and game stats where published、`/api/v1/lol/live` 等 | 低成本候选，但字段稳定性和延迟需实测 | 注册 free/starter，测试 live endpoint 是否足够交易使用 |
| LoLEsports Frontend API | 赛程、event details、match/game metadata、局中 window/details | 已实测 `getSchedule -> getEventDetails -> gameId -> livestats/window/details` 可跑通；历史样本覆盖 final picks、gold、kills、towers、dragons、barons、inhibitors、items | **Phase 0 优先 spike 源**；生产风险来自非官方接口、前端 key 变更、live 延迟未验证、bans 未找到 | 下一场 live match 验证 sourceLatencySec、更新稳定性、暂停状态、覆盖联赛；商业源作为备选/升级 |
| Oracle's Elixir downloads | 历史训练/回测/EGR 系数 | 已验证提供 LCS/LEC/LCK/LPL 等 CSV 下载 | 适合历史模型，不适合实时输入 | 拉取数据，建立 Elo/EGR/history pipeline |
| DraftGap local evaluator | 阵容特征 | 已确认只能作为 draft feature，不做 final probability | 需要外部 BP 输入后才能自动运行 | 复现/封装本地 evaluator；接入 DraftSnapshot |
| 直播 OCR / CV | 免费兜底实时状态 | 未验证；预期维护成本高、延迟高、误识别风险大 | 不作为主线第一版 | 仅在 API 源不可用时作为后备研究 |

---

### 13.3 v0.3 目标模块串联

```text
External Sources
  ├─ Polymarket Gamma / Data / CLOB Public
  ├─ LoLEsports Frontend API
  ├─ Riot / GRID Official Data
  ├─ PandaScore / Abios / Cito
  ├─ Oracle's Elixir historical dataset
  └─ DraftGap local evaluator
        │
        ▼
Collectors
  ├─ PolymarketMarketCollector
  ├─ PolymarketQuoteRecorder
  ├─ ScheduleCollector
  ├─ LiveGameStateConnector
  └─ DraftStateConnector
        │
        ▼
Resolver Layer
  ├─ MarketResolver
  ├─ MatchMapper
  ├─ TeamAliasResolver
  └─ GameNumberResolver
        │
        ▼
Storage
  ├─ markets
  ├─ resolved_markets
  ├─ quotes
  ├─ matches
  ├─ games
  ├─ game_state_snapshots
  ├─ draft_snapshots
  ├─ signals
  ├─ paper_trades
  └─ signal_outcomes
        │
        ▼
Strategy
  ├─ TeamStrengthModel
  ├─ DraftFeatureEngine
  ├─ FairProbabilityEngine
  ├─ EdgeCapacityCalculator
  ├─ SignalEngine
  └─ ExitPlanBuilder
        │
        ▼
Trading / Review
  ├─ PaperBroker
  ├─ SignalJournal
  ├─ MFE/MAE Tracker
  ├─ PriceConvergenceAnalyzer
  └─ UnlockCriteriaEvaluator
```

---

### 13.4 关键模块验收标准

#### 13.4.1 `MarketResolver`

**必须输出：**

```text
resolvedMarketId
polymarketMarketId
conditionId
yesTokenId / noTokenId
league
matchId
gameId
gameNumber
teamA / teamB
blueTeam / redTeam
marketType = game_winner
mappingConfidence
marketStatus
```

**硬门：**

```text
mappingConfidence < 0.90 → 不进入信号层
marketType != game_winner → Phase 1 跳过
gameNumber 不明确 → 跳过
team direction 不明确 → 跳过
```

#### 13.4.2 `LiveGameStateConnector`

**必须输出：**

```text
gameClock
observedAt
sourceTimestamp
sourceLatencySec
blueGold / redGold / goldDiff
blueDragons / redDragons / firstDragonTeam
blueTowers / redTowers
baronStatus / elderStatus
paused / finished / winner
source
confidence
```

**硬门：**

```text
sourceLatencySec 过高 → 只记录，不交易
gameClock 异常回退 → 暂停信号
paused=true → 暂停新信号
confidence 低 → 只记录，不交易
```

#### 13.4.3 `DraftStateConnector`

**必须输出：**

```text
matchId
gameId
patch
blueTeam
redTeam
blueChampions[5]
redChampions[5]
bans
draftComplete
source
sourceLatencySec
confidence
```

**硬门：**

```text
draftComplete=false → 不生成 BP 信号
champion 缺失/无法标准化 → 不生成 BP 信号
blue/red side 不明确 → 不生成 BP 信号
```

#### 13.4.4 `FairProbabilityEngine`

**公式：**

```text
logit_base = logit(TeamStrengthBase)
logit_fair = logit_base + draft_delta + side_delta + patch_delta + live_state_delta
fairProbability = sigmoid(logit_fair)
```

**第一版启用：**

```text
TeamStrengthBase
DraftAdjustment
SideAdjustment
```

**第一版默认关闭，仅记录：**

```text
live_state_delta
15min/EGR
后期价值反转
局中资源错估
```

#### 13.4.5 `EdgeCapacityCalculator`

**必须输出：**

```text
fairProbability
marketBestBid
marketBestAsk
maxBuyPrice
avgFillPrice
worstFillPrice
executableSizeAtEdge
depthUntilEdgeZero
spreadCost
slippageCost
netEdgeAfterSlippage
recommendedSize
capacityScore
```

**核心逻辑：**

```text
maxBuyPrice = fairProbability - minNetEdge
只吃 maxBuyPrice 以下的订单簿深度
若 executableSizeAtEdge < 最小仓位 → 不出交易信号，只记录 watching
```

#### 13.4.6 `ExitPlanBuilder`

**必须输出：**

```text
takeProfitPrice
stopLossPrice
maxHoldMinutes
exitWhenEdgeBelow
invalidateReasons
```

**默认退出条件：**

```text
市场价格接近 fair，netEdge 消失
盘口深度消失或 spread 变宽
BP edge 被局中状态否定
比赛暂停 / 重赛 / 数据源异常
持仓超过 maxHoldMinutes
价格反向突破最大容忍亏损
```

---

### 13.5 主线开发顺序

```text
Step 0: Source Feasibility Spike
  - 验证 Polymarket Game Winner 市场发现 + CLOB public orderbook/WebSocket
  - 优先验证 LoLEsports Frontend API 能自动提供 final picks + derived game clock + gold/objectives
  - 记录 live sourceLatencySec、更新稳定性、暂停/重赛状态、覆盖联赛
  - GRID/PandaScore/Abios/Cito 保留为商业备选或生产升级源

Step 1: Data Foundation
  - Polymarket QuoteRecorder
  - MarketResolver / MatchMapper / TeamAliasResolver
  - LiveGameStateConnector / DraftStateConnector
  - SQLite/Parquet schema

Step 2: Strategy Skeleton
  - TeamStrengthModel 简版 Elo
  - DraftFeatureEngine 接 DraftGap/local evaluator
  - Logit FairProbabilityEngine
  - EdgeCapacityCalculator
  - ExitPlanBuilder

Step 3: Paper Trading Loop
  - SignalEngine
  - PaperBroker
  - MFE/MAE Tracker
  - PriceConvergenceAnalyzer
  - SignalJournal

Step 4: Unlock Review
  - 主线赛前/BP 样本达到门槛后，才逐个解锁 15min/EGR/后期反转

Step 5: Execution Layer（最后）
  - CLOB V2 RealBroker
  - ExecutionGate
  - 私钥/钱包/签名/熔断/对账
```

---

### 13.6 非主线策略解锁标准（草案）

任一冻结策略解锁前，必须满足：

```text
样本数：主线 paper signals ≥ 50，且目标策略观察样本 ≥ 30
净收益：扣 spread/slippage 后 expectancy > 0
价格回归：信号后 X 分钟内向 fair 方向回归比例 > 55%
MFE/MAE：平均 MFE > 平均 MAE
容量：平均 executableSizeAtEdge ≥ $200
延迟损耗：sourceLatencySec 对 MFE 的侵蚀可量化且可接受
联赛切片：LCK/LPL/LEC/国际赛分开看，不能只看总样本
最大回撤：连续亏损与单场亏损低于预设阈值
```

---

### 13.7 当前第一轮验证结论

1. **Polymarket 行情主源可行**：官方文档确认 Gamma/Data API 无认证，CLOB 也有公开 orderbook/price 类端点；Market WebSocket 无认证，可用于 QuoteRecorder。
2. **CLOB V2 必须使用**：旧 `py-clob-client` 已归档并声明不再可用；执行层必须按 V2 设计。
3. **官方实时 LOL 数据源存在但大概率需要申请/付费**：Riot 官方与 GRID 合作分发 LoL Esports live data，包含 gold/objectives 等近实时数据；商业用途通过 GRID。
4. **PandaScore 是商业备选源，不再作为 Phase 0 第一优先**：文档明确 LoL frames 包含 game clock、paused、winner、blue/red gold、towers、kills、drakes、barons、herald、inhibitors、champion 等字段，匹配本项目核心需求；但免费层不足以支撑局中交易，需付费 live plan 才有验证价值。
5. **Abios / Cito 可作为备选源**：Abios 有 REST & Push、Live Play-by-Play；Cito 有 live matches/schedules、pick/ban and game stats where published，但字段深度需要 API key 实测。
6. **LoLEsports Frontend API 升级为 Phase 0 优先 spike 源**：已实测可从 schedule/event 映射到 gameId,并通过 `livestats/window/details` 拉取 final picks、gold、objectives、items 等局中状态。其缺口是 bans 未找到、显式 gameClock 需由 timestamp 推算、live 延迟未验证、接口非官方。
7. **Oracle's Elixir 适合历史模型与 EGR，不适合实时交易输入**。
8. **下一步不是写策略，而是补齐 Source Feasibility Spike 的 live 验证**：优先验证 LoLEsports Frontend API 的 live 延迟与 Polymarket Game Winner 行情闭环。

---

### 13.8 下一步验证任务清单

```text
[x] 实测 LoLEsports Frontend API 历史样本：schedule/event/gameId/window/details 链路已跑通
[ ] 用下一场 live match 验证 LoLEsports Frontend API 的 sourceLatencySec、更新稳定性、暂停状态
[ ] 申请/联系 GRID，确认 LoL official live data 费用、接入门槛、字段、覆盖联赛
[ ] 注册/申请 PandaScore API，作为商业备选验证 live LoL frame 字段与延迟
[ ] 申请 Abios trial，验证 Live Push / Play-by-Play 是否含 gold/objectives/pickban
[ ] 注册 Cito free/starter，验证 /api/v1/lol/live 与 game stats 字段
[ ] 实测 Polymarket Gamma/Data/CLOB public：发现 Game Winner 市场、拿 token/orderbook、订阅 market WS
[ ] 建立 quotes 表与 resolved_markets 表草案
[ ] 定义 SourceScore：officialness / latency / fieldCoverage / cost / reliability / leagueCoverage
[ ] 选择 Phase 1 主输入源组合
```
