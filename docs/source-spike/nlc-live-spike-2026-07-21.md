# NLC Live Spike — 2026-07-21

## Scope

Read-only Phase 0 validation of the public LoL Esports schedule and livestats
`window` / `details` endpoints. No strategy, signal, wallet, order, or private key
was involved.

The current LoL Esports frontend server-rendered the schedule, match IDs, and
game IDs into the public page. The live feed endpoints were then queried directly;
no LoLEsports API key was needed and no historical credential was reused.

## Schedule and mapping evidence

Source: <https://lolesports.com/schedule>

### Arctic Pandas vs Sørby Esports

- League / stage: NLC Summer 2026 / Swiss
- Scheduled start: `2026-07-20T18:00:00Z`
- Format: BO3
- matchId: `116878159559794399`
- Game 1: `116878159559794400`

### Bardicted to U vs Lundqvist Lightside

- League / stage: NLC Summer 2026 / Swiss
- Scheduled start: `2026-07-20T18:00:00Z`
- Format: BO3
- matchId: `116878159559794403`
- Game 1: `116878159559794404`

The official page still serialized both events as `unstarted` while the NLC
broadcast was marked live and both game feeds returned `gameState=in_game`.
This schedule/feed state mismatch must be treated as a source limitation.

## Observations

### Game `116878159559794400`

Observed at `2026-07-20T18:24:14.221911Z`:

- `window` and `details`: HTTP 200 with bodies.
- Final picks, timestamp-derived clock, game state, gold, and objective fields
  were structurally present.
- Latest frame: `2026-07-20T18:06:49.781Z`.
- Derived window latency: `1044.441s`.
- `gameState`: `in_game`.
- Both gold values: `0`.

Conclusion: schema evidence only. The frame was stale by more than 17 minutes,
so this game cannot count as a successful live-latency observation.

### Game `116878159559794404`

Initial observation at `2026-07-20T18:24:40.940865Z`:

- `window` and `details`: HTTP 200 with bodies.
- All required smoke-test fields were structurally present.
- Latest frame: `2026-07-20T18:24:07.671Z`.
- Derived latency: `33.270s` for `window`, `33.716s` for `details`.
- `gameState`: `in_game`.
- Both gold values: `0`.
- Patch: `16.14.794.5912`.
- Final picks were present for both sides.

Repeated observations returned the same latest frame:

| Observed at | Latest frame | Derived window latency | Gold |
|---|---|---:|---:|
| `2026-07-20T18:24:40.940865Z` | `2026-07-20T18:24:07.671Z` | `33.270s` | `0 / 0` |
| `2026-07-20T18:25:09.324288Z` | `2026-07-20T18:24:07.671Z` | `61.653s` | `0 / 0` |
| `2026-07-20T18:25:49.706992Z` | `2026-07-20T18:24:07.671Z` | `102.036s` | `0 / 0` |
| `2026-07-20T18:26:12.209586Z` | `2026-07-20T18:24:07.671Z` | `124.539s` | `0 / 0` |

Conclusion: the feed was initially fresh enough to observe, but it did not
advance during the following 91 seconds and map economy remained zero. This is
consistent with a draft-to-game waiting period or a stalled feed. It is not yet
evidence of stable in-map polling cadence.

## Artifacts

- `lolesports-116878159559794400-window-raw.json`
- `lolesports-116878159559794400-details-raw.json`
- `lolesports-116878159559794400-live-source-smoke.json`
- `lolesports-116878159559794404-window-raw.json`
- `lolesports-116878159559794404-window-raw-20260720T182612Z.json`
- `lolesports-116878159559794404-details-raw.json`
- `lolesports-116878159559794404-live-source-smoke.json`

## Phase 0 judgment

- NLC schedule-to-match-to-game mapping: `observed`, but the public schedule
  state lagged the live feed state.
- Field coverage: `present` for picks, game state, gold, and objectives.
- Explicit game clock: `missing`; only frame timestamps are available.
- Live latency: `partially observed`, with one initially fresh feed and one
  severely stale feed.
- Stable polling cadence: `not validated`.
- Production-safe conclusion: `no`.

The current smoke collector reports `overallOk=true` when required fields are
present even if the frame is stale or contains zero-value pre-map state. Future
probe work should separate schema coverage from live-freshness success.
