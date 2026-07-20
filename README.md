# pm-lol

Polymarket LoL data-source feasibility spike.

This repository is currently in **Phase 0 / conditional Phase 1 data foundation**.
It is used to verify read-only data inputs for League of Legends esports markets
before any strategy, signal, paper trading, wallet, or execution work is allowed.

## Current Scope

The active work is source validation for:

- Polymarket LoL `Game N Winner` market discovery and CLOB orderbook snapshots.
- Cito LoL live state (`gameClock`, gold, objectives, kills, and game state) as
  the conditional primary component, pending multi-match/cross-league stability.
- LoLEsports frontend API draft/final-picks, schedule/mapping, and terminal
  winner supplementation. Active numeric frames observed so far are stale and
  are not accepted as the primary live-state path.
- Market-to-match mapping evidence:
  `market -> match -> gameNumber -> team side`.

Phase 0 is not fully closed. Multi-match/cross-league source stability, an
authoritative team-side source, and repeated live mapping stability are still
required before this can be treated as a production data foundation.

## Boundaries

This project does **not**:

- connect a wallet;
- store private keys;
- call real order placement APIs;
- generate trading signals;
- implement strategy or prediction models;
- authorize live trading.

Any source failure must be recorded as a failure. Do not fake fallback success or
fabricate live data.

## Repository Layout

```text
scripts/                 Read-only spike and smoke scripts
src/pm_lol/              Conditional data foundation package
tests/                   Pytest coverage for parsers, collectors, resolver, smoke helpers
docs/source-spike/       Raw samples, notes, field coverage, and spike evidence
docs/schema-phase1.md    Conditional Phase 1 schema draft
docs/source-score.md     Source scoring and source-role decisions
docs/decision-log.md     Phase and source decisions
roadmap.md               Phase plan and gates
tasks.md                 Current task backlog and evidence requirements
```

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

The Cito smoke script reads `CITO_API_KEY` from the process environment or from
the repository root `.env` file. LoLEsports live probes require
`LOLESPORTS_API_KEY` at runtime; no credential value is stored in the repository.

Example `.env` shape:

```text
CITO_API_KEY=...
```

Never commit `.env` or API keys.

## Verification

QuoteRecorder v1 uses read-only Polymarket REST polling as the current baseline:
Gamma metadata provides market/outcome context and public CLOB `/book` provides
orderbook snapshots. Polymarket WebSocket remains a deferred optimization until a
clean retest passes; it is not a Phase 1 dependency.

Build a local replay SQLite snapshot from checked-in fixtures:

```bash
.venv/bin/python -m pm_lol.replay_pipeline
```

Query quote snapshots by market/game/time range:

```bash
.venv/bin/python scripts/query_quote_snapshots.py \
  --db data/db/replay.db \
  --market-slug lol-ktc-sgw-2026-06-15-game2 \
  --game-number 2
```

Build the replay SQLite snapshot and launch the read-only dashboard:

```bash
.venv/bin/python -m pm_lol.replay_pipeline
npm run dev:dashboard
```

The dashboard serves:

- `http://127.0.0.1:8787/` — compact read-only UI for market mapping, Yes/No
  bestBid/bestAsk, game state, picks, and source status badges.
- `http://127.0.0.1:8787/api/dashboard` — stable JSON contract. Optional query
  filters: `matchId`, `gameId`, `source`, `observedFrom`, `observedTo`.

It reads existing SQLite snapshots only. Fair probability, Polymarket orders,
and strategy signals are disabled placeholders; there is no order, broker,
or secret-bearing module in the dashboard path.

Run the focused tests:

```bash
.venv/bin/python -m pytest tests/test_cito_live_polymarket_smoke.py -q
```

Run the Cito + Polymarket smoke in immediate dry-run mode:

```bash
.venv/bin/python scripts/cito_live_polymarket_smoke.py --poll-timeout-sec 0 --poll-interval-sec 0
```

During a target live window, use the normal polling window:

```bash
.venv/bin/python scripts/cito_live_polymarket_smoke.py --poll-timeout-sec 900 --poll-interval-sec 30
```

The script writes raw samples and a report under `docs/source-spike/`.

## Current Known Risks

- Cito is the conditional primary live-state component, but its observed `24s`
  value is a one-game `sampleAgeSeconds` freshness proxy, not measured
  end-to-end source latency.
- Cito + LoLEsports still need multi-match/cross-league stability evidence.
- The authoritative team-side source is unresolved, and repeated live mapping
  must remain stable at `mappingConfidence >= 0.90`.
- Polymarket REST polling is the QuoteRecorder v1 baseline. Market WebSocket is
  a deferred upgrade and is not a Phase 0 blocker.
- Low-confidence market mappings must be skipped rather than forced.

## Status

The repository tracks `origin/master` at:

```text
https://github.com/zzz163519/pm-lol.git
```

Use `git log --oneline` for the latest pushed commit history.
