# pm-lol

Polymarket LoL data-source feasibility spike.

This repository is currently in **Phase 0 / conditional Phase 1 data foundation**.
It is used to verify read-only data inputs for League of Legends esports markets
before any strategy, signal, paper trading, wallet, or execution work is allowed.

## Current Scope

The active work is source validation for:

- Polymarket LoL `Game N Winner` market discovery and CLOB orderbook snapshots.
- LoLEsports frontend API schedule, event details, and livestats samples.
- Cito LoL schedule/live/visual-state smoke testing as a low-confidence
  candidate source.
- Market-to-match mapping evidence:
  `market -> match -> gameNumber -> team side`.

Phase 0 is not fully closed. Live latency and repeated live/near-live mapping
validation are still required before this can be treated as a production data
foundation.

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
the repository root `.env` file.

Example `.env` shape:

```text
CITO_API_KEY=...
```

Never commit `.env` or API keys.

## Verification

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

- LoLEsports live `sourceLatencySec` is still pending active-match validation.
- Polymarket Market WebSocket still needs clean retest, or REST polling must be
  explicitly accepted as the v1 baseline.
- Cito is not recommended as a primary source until authenticated live samples
  prove field depth, schema stability, league coverage, and latency.
- Low-confidence market mappings must be skipped rather than forced.

## Status

Latest CAL-53 local commit:

```text
02c352b feat(CAL-53): cito live polymarket smoke script, tests, dry-run samples
```

The repository now tracks `origin/master` at:

```text
https://github.com/zzz163519/pm-lol.git
```
