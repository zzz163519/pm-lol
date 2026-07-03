# Decision Log

## Phase 0 Decisions

Date: 2026-06-15

## Data Source Selection

Decision: Use LoLEsports frontend API as the current primary spike source for Phase 1 replay and local pipeline work.

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

Decision: Use Polymarket REST endpoints for Phase 1 local market and orderbook ingestion.

Current evidence:

- Local samples parse market metadata, condition ID, token IDs, outcomes, volume, and orderbook depth.
- Replay writes one market and four quote snapshots from local Polymarket samples.

Risk:

- Market WebSocket remains `pending_risk`; previous notes indicate it needs a clean retest.

## Live Latency Risk

Decision: Mark LoLEsports live latency as `pending_risk`.

Reason:

- Historical samples contain source timestamps, but Phase 0 has not yet measured live `sourceLatencySec` during an active match.
- Until measured, live data can be recorded for replay and paper analysis but should not drive trading decisions.

## Replay Pipeline Result

Decision: Treat the local replay as a data-foundation smoke test, not a market mapping success case.

Result:

- T1 vs GEN LoLEsports samples write match, games, draft snapshots, and game state snapshots.
- Polymarket KT vs Saigon Warriors samples write market and quotes.
- Resolver records a skipped mapping attempt with low confidence because the sample market and LoLEsports match are different events.

## Risk List

| Risk | Status | Impact | Next Action |
|---|---|---|---|
| LoLEsports live latency unknown | `pending_risk` | Could make live signals stale | Measure source latency during an active match. |
| LoLEsports frontend API stability | `pending_risk` | Header/key/schema changes could break ingestion | Add monitoring and fallback source before production. |
| Polymarket Market WebSocket unverified | `pending_risk` | QuoteRecorder may need REST polling fallback | Retest WS subscription on active Game Winner market. |
| Bans unavailable in current LoLEsports samples | `known_gap` | Draft features may be incomplete | Search alternate frontend endpoint or accept picks-only Phase 1. |
| Market-to-match resolver depends on aliases | `known_gap` | Low confidence mappings are skipped | Expand team alias table after more sample markets. |

## Go / No-Go

Recommendation: `GO_FOR_PHASE_1_DATA_FOUNDATION_WITH_GATES`.

Conditions:

- Continue with local replay, SQLite schema, source parsers, and resolver hard gates.
- Do not build strategy, signals, or execution logic yet.
- Do not treat LoLEsports as production primary until live latency is measured.
- Do not rely on Polymarket WebSocket until it is retested; REST orderbook remains acceptable for local replay.

No-go triggers:

- No automatic live source can provide picks plus gold/objectives with acceptable latency.
- Polymarket Game Winner markets cannot be discovered and quoted reliably.
- Resolver cannot reach `mappingConfidence >= 0.90` on real matching events.
