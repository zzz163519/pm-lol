# LoLEsports Live Spike Plan — 2026-07-21

## Status

- Scope: Phase 0 read-only source feasibility only.
- Preparation status: target selected from a live Polymarket Game Winner market.
- Live validation status: first Polymarket-backed observation completed with a
  negative live-source result; see `gen-hle-kespa-live-spike-2026-07-21.md`.
- Credential note: the current LoL Esports page server-renders schedule, match IDs,
  and game IDs. Use that public response plus the unauthenticated livestats feed;
  do not recover or reuse the previously exposed frontend credential.

## Target-selection gate

The workflow is Polymarket-first. A match is eligible only when all of these are
true before LoLEsports probing begins:

1. Polymarket exposes a Game Winner market for the match.
2. The market is `active=true`, `closed=false`, and `acceptingOrders=true`.
3. Both outcome token orderbooks return HTTP 200 and contain at least one bid or ask.
4. The Polymarket teams and scheduled time can be mapped to the official schedule
   without ambiguity.

If any check fails, skip the match. The NLC observations below are retained only
as negative source evidence; they are not an eligible primary test target because
Polymarket had no corresponding markets.

## Schedule evidence

Schedule checked at approximately `2026-07-20T17:58Z` (`2026-07-21 01:58` Asia/Shanghai).

The nearest scheduled matches were simultaneous NLC Swiss-stage BO3s at `2026-07-20T18:00:00Z` (`2026-07-21 02:00` Asia/Shanghai):

- Arctic Pandas vs Sørby Esports
- Lundqvist Lightside vs Bardicted to U

Those matches were too close to the check time to provide a useful pre-match preparation window.

## Completed observation target

- League: KeSPA Cup Group Stage
- Match: Gen.G vs Hanwha Life Esports
- Format: BO1
- Scheduled start: `2026-07-21T06:00:00Z`
- Polymarket event: `lol-gen-hle1-2026-07-21`
- LoL Esports match/game IDs: `116929405156047065` /
  `116929405156047066`

Polymarket remained open with nonempty books, but LoL Esports returned HTTP 204
and Cito remained schedule-only with no live row or numeric state across two
bounded probes. This observation did not close the live-input requirement.

## Next observation target

- League: LES Regular Season
- Match: LUA Gaming vs UB Alma Mater
- Format: BO3
- Scheduled start: `2026-07-21T15:00:00Z`
- Asia/Shanghai: `2026-07-21 23:00` (`UTC+08:00`)
- Polymarket event: `lol-lua-ub-2026-07-21`
- Game 1 Winner: `lol-lua-ub-2026-07-21-game1`
- Game 2 Winner: `lol-lua-ub-2026-07-21-game2`
- Gamma source: <https://gamma-api.polymarket.com/events/slug/lol-lua-ub-2026-07-21>
- Official schedule source: <https://lolesports.com/schedule>

At `2026-07-20T18:39:51Z`, both Game Winner markets were active, open,
accepting orders, and had readable two-sided CLOB books. Game 1 had 36/19
bid/ask levels for LUA and 19/36 for UB; Game 2 had 25/20 and 20/25.

## Cito companion validation

Calvin clarified that the authenticated Cito live payload is expected to expose
accurate match data, with a likely account limit of 10 requests per minute.
Treat that limit as provisional until the authenticated response headers confirm
it. During this Polymarket-backed live window, run Cito as a companion candidate:

- all Cito endpoints share one global budget;
- use 6 requests per minute (10 seconds minimum between calls), below the likely
  10 requests/minute ceiling;
- use schedule/live/coverage only to discover IDs, then poll only visual-state;
- stop on HTTP 429, persist `Retry-After` and rate-limit headers, and do not retry
  within the same probe window;
- validate non-default game clock, gold, objectives, kills and final picks, plus
  frame freshness and post-game reconciliation.

This companion run may change Cito's SourceScore only after live evidence is
captured. The expectation of accurate fields alone does not promote it to a
Phase 1 primary or backup source.

## Pre-flight

Run from the clean worktree:

```bash
cd /home/calvin/pm-lol-live-spike
python scripts/lolesports_live_source_smoke.py --game-id <server-rendered-game-id>
```

Resolve the match and game IDs from the current server-rendered LoL Esports
schedule and require the exact expected start `2026-07-21T15:00:00Z`. The legacy
schedule probe still requires the old frontend credential path and must not be
used for this run. If league, teams, start time, or identifiers conflict with
Polymarket, stop and record a mapping failure; do not guess.

## Live checkpoints

After the probe resolves a `gameId`, collect read-only `window` and `details` samples:

```bash
python scripts/lolesports_live_source_smoke.py --game-id <resolved-game-id>
```

Collect at minimum:

1. Before game start, to record the expected `204`/empty or pre-game behavior.
2. During draft or immediately after the game ID becomes live, to identify when final picks appear.
3. At game start, then at several 5–10 second intervals, to measure frame update cadence and `sourceLatencySec`.
4. During any pause/remake if one occurs; absence of such an event is a limitation, not a pass.
5. After completion, to reconcile event/game state and winner availability.

## Required evidence and pass conditions

- Raw schedule and event-details responses with credential headers excluded.
- Raw `window` and `details` responses for each checkpoint.
- `observedAt`, frame timestamp, HTTP status, request elapsed time, and derived source latency.
- Field coverage for final picks, gold, objectives, game state, and timestamp-derived clock.
- A failure log for every empty body, HTTP error, timeout, parse error, or mapping mismatch.
- No production-safety conclusion from one match. This run can only update source feasibility evidence.

Hard pass criteria for this observation window:

- Polymarket Game Winner market remains open with a readable orderbook.
- Exact league/team/start mapping with no ambiguity.
- Stable readable live frames across multiple consecutive samples.
- Measurable source timestamp and latency.
- Final picks, gold, objectives, and game state present in live responses.

If public schedule IDs or live frames cannot be resolved without reusing the old
credential, record the failure and stop.
