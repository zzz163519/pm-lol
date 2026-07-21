# pm-lol

Polymarket LoL data-source feasibility spike.

This repository is currently in **Phase 0 — Source Feasibility Spike**.
It is used to verify read-only data inputs for League of Legends esports markets
before any strategy, signal, paper trading, wallet, or execution work is allowed.

## Current Scope

The active work is source validation for:

- Polymarket LoL `Game N Winner` market discovery and CLOB orderbook snapshots.
- LoLEsports frontend API schedule, event details, and livestats samples.
- Cito and other unofficial-source evidence retained for comparison only; they
  are not recommended as the Phase 1 primary or backup source.
- Market-to-match mapping evidence:
  `market -> match -> gameNumber -> team side`.

Phase 0 is not closed. LoLEsports active-match field/latency stability,
Polymarket REST/orderbook and WebSocket stability, and repeated live mapping
validation remain open. Phase 1 implementation must not start before they pass.

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
src/pm_lol/              Existing Phase 0 validation assets; no Phase 1 expansion
tests/                   Pytest coverage for parsers, collectors, resolver, smoke helpers
docs/source-spike/       Raw samples, notes, field coverage, and spike evidence
docs/schema-phase1.md    Existing schema draft; not Phase 1 authorization
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

LoLEsports probes read `LOLESPORTS_API_KEY` from the process environment. Cito
comparison probes read `CITO_API_KEY` from the process environment or repository
root `.env` file.

Example `.env` shape:

```text
CITO_API_KEY=...
LOLESPORTS_API_KEY=...
```

Never commit `.env` or API keys.

## Verification

Phase 0 uses read-only Polymarket REST polling for current evidence collection:
Gamma metadata provides market/outcome context and public CLOB `/book` provides
orderbook snapshots. Polymarket WebSocket still requires a clean Phase 0 retest.

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

Capture consecutive read-only frames from a public Twitch event broadcast:

```bash
.venv/bin/python -m pip install -e '.[source-spike]'
.venv/bin/python scripts/twitch_hls_frame_probe.py \
  --channel-url https://www.twitch.tv/kespa2026lck \
  --label bfx-dk-live \
  --sample-count 3 \
  --interval-sec 12
```

This requires `ffmpeg` on `PATH`. The probe stores redacted stream metadata,
timestamped JPEG frames, and a JSON capture report. Signed HLS URLs and their
embedded network data are not persisted.

Run the deterministic visual extractor (no LLM is used at runtime):

```bash
.venv/bin/python -m pip install -e '.[vision-spike]'
.venv/bin/python scripts/visual_frame_extract.py \
  --layout configs/vision/kespa_2026_1920x1080.json \
  sync-templates

.venv/bin/python scripts/visual_frame_extract.py \
  --layout configs/vision/kespa_2026_1920x1080.json \
  extract-sequence frame-01.jpg frame-02.jpg frame-03.jpg \
  --output visual-sequence.json
```

Champion assets remain in `.cache/pm-lol-vision/` and are not committed. The
sequence command preserves every per-frame reading and adds conservative
cross-frame state: clocks must advance, counters cannot roll back, small
objective counters require repeated agreement, and ambiguous champions remain
`unknown`.

## Current Known Risks

- LoLEsports live `sourceLatencySec` is still pending active-match validation.
- Polymarket Market WebSocket still needs a clean retest with a saved message or
  reproducible failure evidence.
- Cito / unofficial sources are not recommended as the Phase 1 primary or backup.
- Twitch HLS is validated only as a visual fallback; OCR/template extraction,
  confidence thresholds, and upstream broadcast delay remain open gates.
- Existing schema, collectors, storage, replay, and dashboard code are frozen as
  validation assets; they are not authorization to expand a Phase 1 skeleton.
- Low-confidence market mappings must be skipped rather than forced.

## Status

The repository tracks `origin/master` at:

```text
https://github.com/zzz163519/pm-lol.git
```

Use `git log --oneline` for the latest pushed commit history.
