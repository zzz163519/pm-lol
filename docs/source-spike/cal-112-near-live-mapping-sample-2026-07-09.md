# CAL-112 Near-Live Mapping Sample

> Observed at: 2026-07-09T14:10:52Z UTC
> Scope: source / market / mapping validation only. No strategy, signal, fair probability, wallet, private key, paper trading, or order execution.

## Candidate Selection

Two near-live candidates were checked from the current Polymarket LoL page and LoLEsports schedule.

1. Prime League, Kaufland Hangry Knights vs Unicorns of Love Sexy Edition
   - Polymarket event: `lol-khk-use1-2026-07-09`
   - Polymarket start: `2026-07-09T16:00:00Z`
   - LoLEsports matchId: `116713163972559036`
   - LoLEsports league: `Prime League`
   - LoLEsports start: `2026-07-09T15:00:00Z`
   - Verdict: good different-league near-live collection target, but not accepted as a Game Winner mapping sample.

2. MSI, G2 Esports vs LYON
   - Polymarket event: `lol-g2-ly-2026-07-10`
   - Polymarket start: `2026-07-10T08:00:00Z`
   - LoLEsports matchId: `115570934355614593`
   - LoLEsports league: `MSI`
   - LoLEsports start: `2026-07-10T08:00:00Z`
   - Verdict: accepted as the near-live Game Winner mapping sample for this evidence card.

## Source Payloads

Raw discovery and mapping artifacts:

- `docs/source-spike/cal-112-g2-ly-near-live-discovery-2026-07-09.json`
- `docs/source-spike/cal-112-g2-ly-near-live-mapping-2026-07-09.json`
- `docs/source-spike/cal-112-primeleague-khk-use-discovery-2026-07-09.json`
- `docs/source-spike/cal-112-primeleague-khk-use-mapping-2026-07-09.json`

G2 vs LYON source requests:

- Polymarket LOL page: HTTP 200
- Gamma event slug `lol-g2-ly-2026-07-10`: HTTP 200
- CLOB `/book` for Game 1 G2 token: HTTP 200
- LoLEsports `getEventDetails?id=115570934355614593`: HTTP 200
- LoLEsports `getSchedule`: HTTP 200
- Total requests: `21`
- Total retries: `0`
- Error classes: `[]`

Prime League source requests:

- Polymarket event slug `lol-khk-use1-2026-07-09`: HTTP 200
- LoLEsports `getEventDetails?id=116713163972559036`: HTTP 200
- LoLEsports `getSchedule`: HTTP 200
- Total requests: `37`
- Total retries: `32`
- Error classes: `["http_error"]`, caused by 404s while the existing script searched older Game Winner CLOB books before finding a live book from another event.

## Polymarket Market

Accepted sample:

- Event slug: `lol-g2-ly-2026-07-10`
- Series question: `LoL: G2 Esports vs LYON (BO5) - Mid-Season Invitational Playoffs`
- Game Winner markets discovered: Game 1, Game 2, Game 3, Game 4
- Game 1 market: `lol-g2-ly-2026-07-10-game1`
- Game 1 conditionId: `0xafa3f92ef06b1f42eeb4239054d133b92b52423bb199350c5f0bfe6eb5aaca94`
- Game 1 G2 tokenId: `76139101447828300858775026719426172181701825631465488526712436980225218230538`
- Game 1 G2 orderbook: `bestBid=0.66`, `bestAsk=0.67`, `bidCount=19`, `askCount=21`

Prime League candidate:

- Event slug: `lol-khk-use1-2026-07-09`
- Series question: `LoL: Kaufland Hangry Knights vs Unicorns Of Love Sexy Edition (BO1) - Prime League 1st Division Regular Season`
- Game Winner markets discovered: `0`
- Series market CLOB token was reachable in a direct spot check, but this repo's Game Winner mapping gate cannot accept a series-only BO1 market as a Game N Winner proof.

## Mapping Sample

Accepted G2 vs LYON mapping:

- `mappingConfidence`: `1.0`
- `viable`: `true`
- `pendingLiveValidation`: `true`
- `startTimeAligned`: `true`
- Polymarket teams: `G2 Esports`, `LYON`
- LoLEsports teams: `LYON`, `G2 Esports`
- Team aliases:
  - `G2 Esports` -> `G2`
  - `LYON` -> `LYON`
- Sample mappings: `8`
- Mapped samples: `8`
- Skipped samples: `0`

Concrete Game 1 token-to-side mapping:

| Outcome | tokenId | LoLEsports gameId | gameNumber | teamId | teamCode | side | confidence |
|---|---|---|---:|---|---|---|---:|
| G2 Esports | `76139101447828300858775026719426172181701825631465488526712436980225218230538` | `115570934355614594` | 1 | `98767991926151025` | G2 | red | 1.0 |
| LYON | `11375244638573387322653973021095160832667152479398725838897146290628938005476` | `115570934355614594` | 1 | `99566405941863385` | LYON | blue | 1.0 |

Prime League mapping candidate:

- `mappingConfidence`: `0.6`
- `viable`: `false`
- `pendingLiveValidation`: `true`
- Reason: team aliases matched, but Polymarket and LoLEsports start times differed by one hour and there were no Game Winner markets to map.

## Timed Collection Task

Run the G2 vs LYON near-live collection every 5 minutes through the match window:

```bash
mkdir -p docs/source-spike/cal-112-runs
timeout 4h bash -lc 'while true; do ts=$(date -u +%Y%m%dT%H%M%SZ); python scripts/polymarket_discovery_smoke.py --target-event-slug lol-g2-ly-2026-07-10 --lolesports-match-id 115570934355614593 --max-events 20 --retries 3 --output docs/source-spike/cal-112-runs/g2-ly-discovery-${ts}.json --mapping-output docs/source-spike/cal-112-runs/g2-ly-mapping-${ts}.json; sleep 300; done'
```

Run the Prime League different-league watch as an explicit pending sample:

```bash
mkdir -p docs/source-spike/cal-112-runs
timeout 3h bash -lc 'while true; do ts=$(date -u +%Y%m%dT%H%M%SZ); python scripts/polymarket_discovery_smoke.py --target-event-slug lol-khk-use1-2026-07-09 --lolesports-match-id 116713163972559036 --max-events 20 --retries 3 --output docs/source-spike/cal-112-runs/primeleague-khk-use-discovery-${ts}.json --mapping-output docs/source-spike/cal-112-runs/primeleague-khk-use-mapping-${ts}.json; sleep 300; done'
```

For cron, use the same command body during the relevant UTC window and escape `%` as `\%` in `date` format strings.

## Pass / Pending Items

Passed:

- Found a near-live Game Winner mapping target with live Polymarket orderbook and LoLEsports match metadata.
- G2 vs LYON reached `mappingConfidence=1.0`.
- Game 1-4 Game Winner markets map to LoLEsports game ids and team sides.
- No strategy, signal, fair probability, wallet, private key, paper trading, or order execution was added or invoked.

Pending:

- This is still near-live / pre-match mapping. It does not close active live latency.
- Prime League gives a different-league near-live target, but it currently fails the Game Winner mapping gate.
- Polymarket WebSocket remains out of scope and pending.
- Full Phase 2 remains frozen until the project owner accepts the broader Phase 0 / Conditional Phase 1 gates.

## Acceptance Conclusion

Accepted for CAL-112 as a second near-live Game Winner mapping sample: `lol-g2-ly-2026-07-10` -> LoLEsports match `115570934355614593`, `mappingConfidence=1.0`, with runnable timed collection commands.

Not accepted as a different-league Game Winner mapping pass: `lol-khk-use1-2026-07-09` / Prime League, because the current Polymarket surface only exposed a series BO1 market and had a one-hour start-time mismatch against LoLEsports.
