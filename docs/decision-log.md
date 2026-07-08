# Decision Log

## Phase 0 Decisions

Date: 2026-06-15

Current status: `CONDITIONAL_PHASE_1_DATA_FOUNDATION`.

This is not full Phase 1 approval and not permission to start strategy, edge,
signals, paper trading, wallet integration, private key handling, broker code,
or real order placement. The existing Phase 1 data foundation skeleton is
treated as local validation tooling only.

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

Decision: Use LoLEsports frontend API as the current primary spike source for
local replay and conditional Phase 1 data foundation work.

Rationale:

- Existing local samples prove the path from event details to game IDs, final picks, patch, and 15-minute game state.
- The source is free and requires no external key for the current replay pipeline.
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

Decision: Use Polymarket REST endpoints for conditional Phase 1 local market
and orderbook ingestion.

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
conditional data-foundation work via HTML slug discovery, Gamma slug detail, and
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

Decision: Treat the existing Python package, SQLite schema, collectors,
resolver, and replay pipeline as a conditional data-foundation validation
skeleton.

Evidence:

- `docs/schema-phase1.md` defines the Phase 1 tables.
- `pyproject.toml`, `src/pm_lol/`, and `tests/` exist.
- Local tests cover source parsing, collectors, storage, resolver behavior, and
  replay smoke.

Boundary:

- This does not close Phase 0 hard gates.
- This does not start Phase 2.
- No strategy, signal, fair probability, broker, wallet, private key, or real
  order placement code is allowed.

## Risk List

| Risk | Status | Impact | Next Action |
|---|---|---|---|
| LoLEsports live latency unknown | `pending_risk` | Could make live signals stale | Measure source latency during an active match. |
| LoLEsports frontend API stability | `pending_risk` | Header/key/schema changes could break ingestion | Add monitoring and fallback source before production. |
| Polymarket Market WebSocket unverified | `deferred_network_retest` | QuoteRecorder v1 uses REST polling baseline | Retest WS subscription on active Game Winner market before upgrading. |
| Polymarket generic search unreliable | `known_gap` | Market discovery may miss or mis-rank LoL markets | Use page HTML slug discovery plus Gamma slug detail, not generic search alone. |
| Polymarket network path unstable | `pending_network_retest` | Collectors may see intermittent TLS failures | Add retry/backoff and classify SSL/proxy/direct failures during source spike. |
| Bans unavailable in current LoLEsports samples | `known_gap` | Draft features may be incomplete | Search alternate frontend endpoint or accept picks-only Phase 1. |
| Market-to-match resolver depends on aliases | `known_gap` | Low confidence mappings are skipped | Expand team alias table after more sample markets. |
| Real cross-event mapping unproven | `pending_risk` | Markets cannot be trusted without high-confidence match/game/team mapping | Capture a true same-match Polymarket and LoLEsports sample with `mappingConfidence >= 0.90`. |

## Go / No-Go

Recommendation: `CONDITIONAL_PHASE_1_DATA_FOUNDATION`.

Conditions:

- Continue with local replay, SQLite schema, source parsers, collectors, storage,
  and resolver hard gates.
- Do not build strategy, signals, or execution logic yet.
- Do not treat LoLEsports as production primary until live latency is measured.
- Do not rely on Polymarket WebSocket until it is retested; REST orderbook remains acceptable for local replay.
- Do not treat any market mapping as passed until a real matching event reaches
  `mappingConfidence >= 0.90`.

No-go triggers:

- No automatic live source can provide picks plus gold/objectives with acceptable latency.
- Polymarket Game Winner markets cannot be discovered and quoted reliably.
- Resolver cannot reach `mappingConfidence >= 0.90` on real matching events.

## 2026-07-08 — 策略定位：不追求秒级延迟，主源定为 Cito

**决策人**：Calvin

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
