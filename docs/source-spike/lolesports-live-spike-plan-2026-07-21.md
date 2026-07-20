# LoLEsports Live Spike Plan — 2026-07-21

## Status

- Scope: Phase 0 read-only source feasibility only.
- Preparation status: ready except for runtime credential injection.
- Live validation status: not started.
- Blocker: `LOLESPORTS_API_KEY` is not present in the current runtime. Do not reuse the previously exposed credential; inject a current rotated value at execution time.

## Schedule evidence

Schedule checked at approximately `2026-07-20T17:58Z` (`2026-07-21 01:58` Asia/Shanghai).

The nearest scheduled matches were simultaneous NLC Swiss-stage BO3s at `2026-07-20T18:00:00Z` (`2026-07-21 02:00` Asia/Shanghai):

- Arctic Pandas vs Sørby Esports
- Lundqvist Lightside vs Bardicted to U

Those matches were too close to the check time to provide a useful pre-match preparation window.

## Selected observation target

- League: KeSPA Cup
- Stage: Groups
- Match: Hanwha Life Esports vs Gen.G Esports
- Format: BO1
- Scheduled start: `2026-07-21T06:00:00Z`
- Asia/Shanghai: `2026-07-21 14:00` (`UTC+08:00`)
- Primary schedule source: <https://lolesports.com/schedule>
- Cross-check: <https://www.sofascore.com/esports/match/hanwha-life-esports-geng/IFVcsROVc>

The selected target is not the chronologically nearest match. It is the next practical window with enough lead time to resolve `matchId`/`gameId` and observe pre-game, draft-to-game transition, and live frames.

## Pre-flight

Run from the clean worktree:

```bash
cd /home/calvin/pm-lol-live-spike
test -n "$LOLESPORTS_API_KEY"
python scripts/lolesports_t1_g2_livestats_probe.py \
  --target-team "Hanwha Life Esports" \
  --target-team "Gen.G Esports" \
  --expected-start "2026-07-21T06:00:00Z" \
  --game-number 1
```

The expected start is mandatory for this run because the same teams can meet repeatedly. If the returned league, teams, start time, or match identifier conflicts with the schedule evidence, stop and record a mapping failure; do not guess.

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

- Exact league/team/start mapping with no ambiguity.
- Stable readable live frames across multiple consecutive samples.
- Measurable source timestamp and latency.
- Final picks, gold, objectives, and game state present in live responses.

If the credential is missing or rejected, record `credential_missing` or `credential_rejected` and do not claim the live spike ran.
