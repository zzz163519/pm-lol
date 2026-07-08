# Cito / Polymarket Live Loop Report

Date: 2026-07-08 UTC

## Scope

Read-only CAL-54 live-loop validation. No wallet, private key, order placement,
strategy, prediction model, or trading signal path was used.

## Commands

```bash
python scripts/cito_live_polymarket_smoke.py \
  --event-slug lol-g2-t1-2026-07-08 \
  --event-slug lol-ly-tsw-2026-07-08 \
  --poll-timeout-sec 60 \
  --poll-interval-sec 15

.venv/bin/pytest tests/test_cito_live_polymarket_smoke.py -q
```

## Raw Samples

- Main report: `docs/source-spike/cito-live-polymarket-smoke-2026-07-08.json`
- Cito schedule: `docs/source-spike/cito-schedule-today-dry-run-2026-07-08.json`
- Cito live discovery: `docs/source-spike/cito-live-dry-run-2026-07-08.json`
- Cito coverage precheck: `docs/source-spike/cito-coverage-115570934355614588-2026-07-08.json`
- Cito visual-state: `docs/source-spike/cito-visual-state-115570934355614588-2026-07-08.json`
- Cito live stats: `docs/source-spike/cito-stats-115570934355614588-2026-07-08.json`
- Cito postgame enrichment: `docs/source-spike/cito-postgame-115570934355614588-2026-07-08.json`
- Polymarket CLOB snapshot: `docs/source-spike/cito-polymarket-clob-dry-run-2026-07-08.json`

## Findings

Overall status: `live_visual_state_not_ready`.

Cito `/api/v1/lol/schedule/today` returned 13 matches. The relevant live row was:

```text
matchId: 115570934355614587
gameId: 115570934355614588
teams: LYON vs Team Secret Whales
state: inProgress
league: MSI
```

Cito `/api/v1/lol/live` returned `status=live` and exposed the match row, but
coverage precheck still reported:

```text
coverage_level: live_listed
live_row: true
schedule_metadata: true
numeric_live_state: false
expected_live_state: false
expected_webhooks: false
```

The visual-state endpoint was reachable with HTTP 200 for game
`115570934355614588`, but returned `status=not_ready` and `data=null`. The
stats endpoint also returned `status=not_ready`; postgame enrichment returned
`coverageLevel=none` with no available sections.

Polymarket Gamma discovery and CLOB snapshot succeeded for the first supplied
slug with available Game Winner markets, `lol-g2-t1-2026-07-08`. The Cito live
row at the sample time was LYON vs TSW, so the captured Cito live row and the
captured Polymarket orderbook are not a same-match proof. Use the existing
LYON/TSW prematch mapping sample for static same-event mapping evidence.

## Field Coverage

| Field | Result | Evidence |
|---|---|---|
| Schedule | present | `/schedule/today` returned current MSI rows |
| Match id | present | live row `matchId=115570934355614587` |
| Game id | present via coverage | coverage games included `esportsApiId=115570934355614588` |
| Team identity | present in live/coverage | LYON and Team Secret Whales |
| Game clock | missing | visual-state `not_ready`, stats `not_ready` |
| Gold | missing | `numeric_live_state=false` |
| Objectives | missing | `numeric_live_state=false` |
| Game state | partial | schedule/live row is in progress; no numeric game state |
| Winner | missing | no completed game/postgame coverage |
| Final picks | missing | no draft or final stats payload in this run |

## Latency

`sourceLatencySec` for Cito live game state is not computable from this sample:
Cito did not provide a game clock, source timestamp, or numeric live-state frame.

Recorded request timing only:

```text
citoSnapshotAt: 2026-07-08T03:03:44.440990Z
polymarketSnapshotAt: 2026-07-08T03:03:46.654206Z
citoVsPolymarketDeltaSec: 2.213
```

This is request skew between two snapshots, not live-source latency.

## Conclusion

```text
cito_live_discovery = usable_for_live_listed_match_detection
cito_numeric_live_state = not_validated
cito_visual_state = reachable_but_not_ready
cito_sourceLatencySec = not_computable
polymarket_clob_snapshot = readable
same_match_live_cito_polymarket_proof = not_obtained_in_this_run
```

Cito should not be promoted to a Phase 1 primary or backup live source from this
sample. The next useful run should keep polling until coverage reports
`numeric_live_state=true`, then capture visual-state/stats and same-match
Polymarket CLOB in the same sampling window.
