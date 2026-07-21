# Gen.G vs Hanwha Life Esports KeSPA Cup Live Spike

## Scope

Read-only Phase 0 validation of Polymarket, the public LoL Esports schedule and
livestats feed, and authenticated Cito. No strategy, prediction, signal, wallet,
private key, order placement, or execution path was used.

## Target mapping

- Match: Gen.G vs Hanwha Life Esports, KeSPA Cup Group Stage, BO1
- Scheduled start: `2026-07-21T06:00:00Z` (`14:00` Asia/Shanghai)
- Polymarket event: `lol-gen-hle1-2026-07-21`
- LoL Esports match ID: `116929405156047065`
- LoL Esports Game 1 ID: `116929405156047066`
- Cito schedule match ID: `lol-match-116929405156047065`

The team names, start time, match ID, and game ID were recovered without
ambiguity from the public server-rendered LoL Esports schedule page. No legacy
LoL Esports frontend credential was recovered or reused.

## Observations

### Polymarket

At `2026-07-21T06:17:13Z`, the Game Winner market was `active=true`,
`closed=false`, and `acceptingOrders=true`. Gamma reported Gen.G at
approximately `0.31 / 0.32`.

At `2026-07-21T06:24:35Z`, both CLOB books were readable and nonempty:

| Outcome | Best bid | Best ask | Bid levels | Ask levels |
|---|---:|---:|---:|---:|
| Gen.G | `0.24` | `0.25` | 23 | 58 |
| Hanwha Life Esports | `0.75` | `0.76` | 58 | 23 |

The large price movement confirms an active market, but it is not proof by
itself that the game had entered an official live state.

### LoL Esports

- At `2026-07-21T06:19:36Z`, both `window` and `details` returned HTTP 204
  with empty bodies for Game 1.
- At `2026-07-21T06:22:46Z`, both endpoints still returned empty bodies.
- At `2026-07-21T06:23:03Z`, a fresh public schedule page still serialized the
  event as `state=unstarted`.
- At `2026-07-21T06:26:00Z`, direct HTTP checks again returned HTTP 204 with
  zero response bytes for both endpoints.

No final picks, frame timestamp, derived game clock, gold, kills, towers,
dragons, barons, or game state were available during the observation window.

### Cito

The first probe ran from `2026-07-21T06:18:17Z` to
`2026-07-21T06:21:34Z`:

- 19 authenticated GET requests
- minimum interval `10.352s`
- maximum observed request rate `5.809 requests/minute`
- zero HTTP 429 responses
- schedule match found, but `/lol/live` remained `no_match`
- `live_row=false`, `numeric_live_state=false`, and no game ID

The second probe ran from `2026-07-21T06:24:56Z` to
`2026-07-21T06:26:45Z`:

- 11 authenticated GET requests
- minimum interval `10.356s`
- zero HTTP 429 responses
- the same `no_match`, `live_row=false`, and `numeric_live_state=false` result

Cito classified KeSPA Cup as `opportunistic_live_state` with schedule-only
coverage in both probes. All requested live fields remained missing.

## Phase 0 judgment

- Polymarket market discovery and CLOB readability: **pass for this window**.
- Exact schedule/team/game mapping: **pass**.
- LoL Esports live frame availability: **fail for this window**.
- Cito live row and numeric field availability: **fail for this window**.
- Cross-source live input closure: **not achieved**.

This match cannot validate either LoL Esports or Cito as a usable KeSPA Cup
live input. The evidence also rejects treating Cito schedule coverage as live
coverage: Phase 1 eligibility must require `live_row=true` and
`numeric_live_state=true`, not merely a matched schedule row. A later positive
sample may establish feasibility for another league, but it must not overwrite
this KeSPA Cup coverage failure.

## Artifacts

- `polymarket-gen-hle-event-raw-20260721T062435Z.json`
- `polymarket-gen-hle-gen-book-raw-20260721T062435Z.json`
- `polymarket-gen-hle-hle-book-raw-20260721T062435Z.json`
- `lolesports-116929405156047066-live-source-smoke.json`
- `cito-t1-g2-field-probe-20260721T061817288Z.json`
- `cito-t1-g2-field-probe-20260721T061817288Z.md`
- `cito-t1-g2-field-probe-20260721T062456668Z.json`
- `cito-t1-g2-field-probe-20260721T062456668Z.md`

The Cito artifact filename retains the probe script's historical name; the
embedded target and report content correctly identify Gen.G and Hanwha Life
Esports.
