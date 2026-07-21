# Decision Log

## Phase 0 Decisions

Date: 2026-07-21

Current status: `PHASE_0_SOURCE_FEASIBILITY_SPIKE`.

Phase 1 is not started. This is not permission to expand the existing code into
a Phase 1 skeleton or to start strategy, models, signals, paper trading, wallet
integration, private key handling, broker code, or real order placement.
Existing schema, collectors, storage, replay, resolver, and dashboard code are
frozen as Phase 0 validation assets.

DoD decision:

- Code cards cannot be accepted from a local dirty tree only; they must have a
  PR. No PR means not accepted.
- Documentation cards should also use a PR when repository files change. If a
  run only posts a documentation comment and does not change the repo, it must
  say so explicitly.

Secret hygiene decision:

- API key / token values must never be pasted into issue comments.
- API key / token values must never be written into artifacts, logs, sample
  payloads, or docs.
- Any leaked key/token must be treated as compromised and rotated.

## Data Source Selection

Decision: Use LoLEsports frontend API as the current Phase 0 primary spike source.

Rationale:

- Existing local samples prove the path from event details to game IDs, final picks, patch, and 15-minute game state.
- The source requires runtime `LOLESPORTS_API_KEY` injection; no credential is stored in the repository.
- It is not yet accepted as production-safe because live latency and stability are not validated.

Backup decision: Keep PandaScore as the commercial backup candidate.

Rationale:

- Expected live frame fields align with Phase 1 needs.
- It likely requires paid live access, so it is not the cheapest first path.

Upgrade decision: Keep GRID as the best-quality future source.

Rationale:

- It is the official/commercial live data path.
- Cost, contract, and access constraints make it unsuitable as the default spike input.

Rejected or limited sources:

- Oracle's Elixir: useful for historical research, not live trading input.
- Cito / unofficial sources: insufficient proof of live depth, coverage, and reliability.

## Polymarket Market Data

Decision: Use Polymarket REST endpoints for Phase 0 market and orderbook evidence.

Current evidence:

- Local samples parse market metadata, condition ID, token IDs, outcomes, volume, and orderbook depth.
- Replay writes one market and four quote snapshots from local Polymarket samples.
- 2026-07-03 retest confirms current LOL `Game N Winner` discovery is viable by
  fetching the Polymarket LOL page HTML for event slugs, calling Gamma
  `/events/slug/{slug}`, filtering `Game [1-5] Winner`, and reading CLOB
  `/book` for token-level bids/asks.
- Current event slugs observed from the page: `lol-ly-fur-2026-07-03`,
  `lol-blg-t1-2026-07-04`, `lol-tsw-tes-2026-07-04`, and
  `lol-hle1-g2-2026-07-05`.
- Gamma slug detail confirmed Game 1/2/3/4 Winner markets for current MSI
  examples. No `Game 5 Winner` market was observed in those samples; only some
  Game 5 props were visible.
- CLOB `/book` was validated for `lol-blg-t1-2026-07-04-game1`, conditionId
  `0x52671a734b1872bab38ddaf5113a4716fb81b5bfb9e794475fadbea0fbacf0cf`,
  with the Bilibili Gaming token showing `bids=30`, `asks=31`,
  `bestBid=0.47`, and `bestAsk=0.48`.

Risk:

- Market WebSocket remains `pending_network_retest`; previous notes indicate it
  needs a clean retest. REST polling is acceptable as the QuoteRecorder v1
  baseline unless WS is later validated.
- Gamma generic keyword search is not reliable for LoL discovery; searches for
  `league of legends`, `lol`, and `t1` can return unrelated markets such as
  Kraken IPO, Macron, and UK election markets.
- The current WSL/proxy/direct network path is unstable for Polymarket domains.
  `SSL_ERROR_SYSCALL` and browser `ERR_CONNECTION_CLOSED` are interpreted as
  network/TLS negotiation instability, not proof that Polymarket LOL markets are
  unavailable. `curl --http1.1` is not a universal workaround because it also
  failed in the 2026-07-03 retest.

Decision update on 2026-07-03: Polymarket LOL Game Winner source is viable for
Phase 0 evidence collection via HTML slug discovery, Gamma slug detail, and
CLOB REST polling, with retry/backoff and explicit error classification. It is
not production-safe until WebSocket and network-path stability are retested.

## Live Latency Risk

Decision: Mark LoLEsports live latency as `pending_risk`.

Reason:

- Historical samples contain source timestamps, but Phase 0 has not yet measured live `sourceLatencySec` during an active match.
- Until measured, live data can be recorded for replay and source-quality
  analysis but must not drive strategy, signals, or execution decisions.

## Replay Pipeline Result

Decision: Treat the local replay as a data-foundation smoke test, not a market mapping success case.

Result:

- T1 vs GEN LoLEsports samples write match, games, draft snapshots, and game state snapshots.
- Polymarket KT vs Saigon Warriors samples write market and quotes.
- Resolver records a skipped mapping attempt with low confidence because the sample market and LoLEsports match are different events.

## Local Data Foundation Skeleton

Decision: Freeze the existing Python package, SQLite schema, collectors,
resolver, replay pipeline, and dashboard as Phase 0 validation assets.

Evidence:

- `docs/schema-phase1.md` defines the Phase 1 tables.
- `pyproject.toml`, `src/pm_lol/`, and `tests/` exist.
- Local tests cover source parsing, collectors, storage, resolver behavior, and
  replay smoke.

Boundary:

- This does not close Phase 0 hard gates.
- This does not authorize new Phase 1 skeleton work.
- This does not start Phase 2.
- No strategy, signal, fair probability, broker, wallet, private key, or real
  order placement code is allowed.

## Risk List

| Risk | Status | Impact | Next Action |
|---|---|---|---|
| LoLEsports live latency unknown | `pending_risk` | Could make live signals stale | Measure source latency during an active match. |
| LoLEsports frontend API stability | `pending_risk` | Header/key/schema changes could break ingestion | Add monitoring and fallback source before production. |
| Polymarket Market WebSocket unverified | `phase0_open_gate` | Push-path stability is unknown | Retest WS subscription on an active Game Winner market and save a message or reproducible failure evidence. |
| Polymarket generic search unreliable | `known_gap` | Market discovery may miss or mis-rank LoL markets | Use page HTML slug discovery plus Gamma slug detail, not generic search alone. |
| Polymarket network path unstable | `pending_network_retest` | Collectors may see intermittent TLS failures | Add retry/backoff and classify SSL/proxy/direct failures during source spike. |
| Bans unavailable in current LoLEsports samples | `known_gap` | Draft features may be incomplete | Search alternate frontend endpoint or accept picks-only Phase 1. |
| Market-to-match resolver depends on aliases | `known_gap` | Low confidence mappings are skipped | Expand team alias table after more sample markets. |
| Live mapping team side unstable | `pending_risk` | Match/game/team and market/token identity are high-confidence, but side-dependent consumers could bind a token to the wrong side | Identify the authoritative side source and require stable sides across repeated live samples. |

## Go / No-Go

Recommendation: `PHASE_0_NO_GO`.

Conditions:

- Continue only read-only source spikes, schema drafts, raw evidence collection,
  and mapping hard-gate validation.
- Do not expand Phase 1 code or build strategy, models, signals, or execution logic.
- Do not treat LoLEsports as production primary until live latency is measured.
- Complete the Polymarket REST/orderbook stability run and WebSocket clean retest before closing Phase 0.
- Do not treat the complete market-to-team-side mapping as passed until a real
  matching event reaches `mappingConfidence >= 0.90` and repeated live samples
  keep team sides stable.

No-go triggers:

- No automatic live source can provide picks plus gold/objectives with acceptable latency.
- Polymarket Game Winner markets cannot be discovered and quoted reliably.
- Resolver cannot reach `mappingConfidence >= 0.90` on real matching events.

## 2026-07-08 — 历史决策：不追求秒级延迟，主源定为 Cito（已取代）

**决策人**：Calvin

**状态**：该数据源角色决策已被 2026-07-21 Phase 0 治理校准取代。以下内容仅保留历史记录，不再作为当前主源选择或阶段授权。

**决策**：项目策略为错配/价值交易模型，对延迟敏感度低。Cito median 24s 延迟可接受，不再作为 Phase 0 blockers。

**主源组合**：
- Cito API：team identity / gold / goldDiff / objectives / kills / gameClock / gameState（CAL-59 fc8f1a6 验证）
- LoLEsports Frontend API：draft/picks 补充（CAL-59 ec7b4fd 验证）

**Phase 0 剩余 gates**：
- Cito + LoLEsports 字段组合多场次稳定性复核
- 映射准确性 ≥ 0.90 复核（更多赛事/联赛）
- Polymarket WS retest 或正式记录 REST polling 为 baseline

**作废**：
- CAL-56（找更低延迟源）→ 标 cancelled，原因：项目不追求秒级延迟
- CAL-55（Cito 延迟量化）→ 降为 backlog，延迟数字已有参考值，不是 blocker

## 2026-07-10 — CAL-157 G2 vs LYON 真实赛中映射复核

**证据**：在 `2026-07-10T09:48:38.926396Z` 和
`2026-07-10T09:54:44.462731Z` 两次只读采样。LoLEsports match
`115570934355614593` 均为 `inProgress`，Game 3 均为 `inProgress`；不是 pre-match
static 样本。Polymarket event `lol-g2-ly-2026-07-10` 的 Game 1-4 market、
conditionId、tokenId 与 LoLEsports match/game/team identity 均稳定，两个样本的
`mappingConfidence` 均为 `1.0`。每次 15 个 source 请求全部成功、零重试。

**发现**：Game 3 的 team side 在 365.536335 秒内从 G2 red / LYON blue 翻转为
G2 blue / LYON red；当前 confidence 计算未反映该跨样本不稳定性。

**决策**：真实赛中证据捕获 PASS；match/game/team identity 与
Polymarket market/token mapping PASS；完整 team-side stability PENDING。CAL-112
保持 NO-GO，直到确认 authoritative side source 并用重复 live 样本证明 side 稳定。
LoLEsports live latency 仍为 `pending_risk`，因为 event details 无 source timestamp。
Phase 2 继续冻结。

**Artifacts**：

- `docs/source-spike/cal-157-g2-ly-live-mapping-evidence-20260710T094838Z.json`
- `docs/source-spike/cal-157-g2-ly-live-mapping-report-20260710T094838Z.md`
- `docs/source-spike/cal-157-g2-ly-discovery-20260710T094838Z.json`
- `docs/source-spike/cal-157-g2-ly-mapping-20260710T094838Z.json`
- `docs/source-spike/cal-157-g2-ly-discovery-20260710T095444Z.json`
- `docs/source-spike/cal-157-g2-ly-mapping-20260710T095444Z.json`

## 2026-07-10 — CAL-157 authenticated CITO no-active-match 重跑

**证据**：`2026-07-10T10:50:59.151801Z` 起使用仅存在于进程环境的
`CITO_API_KEY` 执行 authenticated read-only GET。CITO `/lol/live` 返回 HTTP 200、
业务状态 `no_match`、`count=0`、`liveOnly=true`；`/lol/schedule/today` 返回 HTTP
200、`partial_data`、`dataFreshness=fresh`，并把 G2 vs LYON match
`115570934355614593` 标为 completed、LYON 3–0。CITO 明确警告 schedule 数据经
Riot LoL Esports event details 修复，因此不把它伪装成独立 live 确认。

同一重跑窗口内，CITO Game 3 visual-state 返回 HTTP 200 / `no_live_match`；
LoLEsports event details 显示 match 与 Games 1–3 completed，Game 3 final picks
仍可从 livestats window 读取；Polymarket public Gamma/CLOB REST 仍可读取 Game
1–4 condition/token mapping，`mappingConfidence=1.0`，orderbook source timestamp
距 discovery observation 37.534 秒。

**决策**：这是 `no-active-match/near-live` 证据，不是 live 证据。identity PASS；
game PENDING；team side PENDING；market token side PASS。Authenticated CITO read
access 已验证，但 active-match CITO live numeric fields 与 authoritative team-side
stability 尚未验证。CAL-112 保持 NO-GO，Phase 2 继续冻结。

**Artifacts**：

- `docs/source-spike/cal-157-cito-cross-validation-20260710T105059Z.json`
- `docs/source-spike/cal-157-cito-cross-validation-20260710T105059Z.md`

## 2026-07-21 — Phase 0 治理校准

**决策人**：Calvin

**当前阶段**：`PHASE_0_SOURCE_FEASIBILITY_SPIKE`。撤销
`CONDITIONAL_PHASE_1_DATA_FOUNDATION` 作为当前状态；Phase 0 完成前不得启动或扩建
Phase 1 代码骨架。

**当前数据源角色**：

- 主 spike：LoLEsports Frontend API；active-match latency/field stability 未通过前不视为生产安全。
- 盘口：Polymarket public REST/orderbook；Market WebSocket 仍需 clean retest。
- 商业备选：PandaScore；未来升级：GRID。
- 历史研究：Oracle's Elixir，不作为 live 输入。
- Cito / 非官方源：保留历史比较证据，但不推荐作为 Phase 1 主源或备源。

**Phase 0 剩余硬门**：

- LoLEsports active-match final picks、game clock、gold、objectives、字段稳定性与 `sourceLatencySec`。
- Polymarket Game Winner discovery、REST/orderbook 重复稳定性与 WebSocket clean retest。
- 多场真实 `market -> match -> gameNumber -> team/outcome side` 映射稳定，
  `mappingConfidence >= 0.90`；低置信度必须 skip。

**边界**：现有 schema、collector、storage、resolver、replay、dashboard 仅作为 Phase 0
验证资产冻结保留。不得新增策略、预测模型、交易信号、paper trading、钱包、私钥、
broker、order 或真实下单能力。

## 2026-07-21 — Cito active-match 复测与共享限流预算

Calvin 澄清：Cito 应能提供准确的实时比赛字段，当前账户限制预计为 10 requests/minute。
该限制先作为待响应头确认的运行假设，不直接推翻既有 SourceScore 结论。

下一次只选择已有 Polymarket Game Winner 活跃盘口的比赛做 authenticated read-only
复测。所有 Cito 端点共享 6 requests/minute 的全局预算（请求间隔至少 10 秒）；完成
schedule/live/coverage ID 发现后只轮询 visual-state。HTTP 429 时立即停止，记录
`Retry-After` 与 rate-limit headers，不在同一窗口自动重试。

只有在 LUA Gaming vs UB Alma Mater 或后续同类 Polymarket-backed active match 中，
验证 non-default game clock、gold、objectives、kills、final picks、freshness 及赛后对账后，
才重新评分并决定 Cito 是否可成为 Phase 1 主源或备源。

## 2026-07-21 - Strategy semantics: conditional value, not speed

Decision owner: Calvin.

The PM-LOL thesis is confirmed as conditional probability value trading. Team strength supplies the prior; final picks supply an early/mid/late composition power curve; economy, objectives and map state update win probability conditionally against that curve. The strategy searches for executable Polymarket Game Winner prices below the calibrated conditional probability after costs.

Source delay is accepted when the observed state remains valid and sufficient net value remains. The strategy does not require first-event detection or short-horizon repricing. Resolution EV and price-convergence exits must be evaluated separately.

A weak or low-ranked team, a current gold deficit, or high odds is not an automatic buy. A future high-odds reversal path requires unrealized scaling, a survivable trajectory, non-terminal game state, executable net value and calibrated low-probability evidence.

`docs/strategy-model-semantics.md` supersedes earlier fixed-delta or speed-dependent interpretations. This is a documentation clarification only; Phase 0 prohibitions on model, signal, paper-trading and execution implementation remain unchanged.
