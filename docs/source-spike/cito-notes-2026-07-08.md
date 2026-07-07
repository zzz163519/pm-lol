# Cito / LoLEsportsAPI Phase 0 Spike

Date: 2026-07-08 Asia/Shanghai

## Scope

Read-only validation for Cito as a low-cost Phase 0 LoL live source candidate.
No wallet, private key, trading, signal, strategy, or production daemon work was
performed.

## Access Result

Blocked for authenticated Cito validation.

The local process did not expose a Cito API key environment variable. I checked
only environment variable names matching `CITO|LOL|POLYMARKET|API` and did not
print any secret values.

Unauthenticated probes were sent without an API key:

| Endpoint | HTTP status | Error code | Raw response |
|---|---:|---|---|
| `GET https://api.citoapi.com/api/v1/lol/live` | 401 | `MISSING_API_KEY` | `docs/source-spike/cito-no-key-2026-07-08.http` |
| `GET https://api.citoapi.com/api/v1/lol/schedule/upcoming` | 401 | `MISSING_API_KEY` | `docs/source-spike/cito-no-key-2026-07-08.http` |
| `GET https://api.citoapi.com/api/v1/lol/live/115570934355614576/visual-state` | 401 | `MISSING_API_KEY` | `docs/source-spike/cito-no-key-2026-07-08.http` |

Observed response headers included `RateLimit-Policy: 1000;w=60`,
`RateLimit-Limit: 1000`, and decreasing `RateLimit-Remaining` values, but this
is only the unauthenticated error path. Do not treat it as the account plan's
usable request limit.

## Public Documentation Findings

Public docs and the LoLEsportsAPI microsite were reachable through Jina Reader:

- `https://citoapi.com/docs/api/league-of-legends`
- `https://lolesportsapi.com/`

Documented auth shape:

```text
x-api-key: YOUR_CITO_API_KEY
```

Documented Phase 0-relevant endpoints:

- `GET /api/v1/lol/coverage`
- `GET /api/v1/lol/live`
- `GET /api/v1/lol/matches/live`
- `GET /api/v1/lol/matches/{matchId}/coverage`
- `GET /api/v1/lol/live/{matchId}/series`
- `GET /api/v1/lol/live/{gameId}/visual-state`
- `GET /api/v1/lol/schedule/today`
- `GET /api/v1/lol/schedule/upcoming`
- `GET /api/v1/lol/matches/{id}`
- `GET /api/v1/lol/matches/{id}/games`
- `GET /api/v1/lol/games/{gameId}/stats`
- `GET /api/v1/lol/games/{gameId}/timeline`
- `GET /api/v1/lol/analytics/drafts/{matchId}`
- `GET /api/v1/lol/webhooks/events`

Documented live-field claims:

- `visual-state`: game time, gold, kills, towers, dragons, and barons where
  available.
- `live/{matchId}/series`: completed games, score, and current game context.
- `matches/{matchId}/coverage`: pre-check for schedule metadata, live row,
  numeric live state, and webhook eligibility.
- `analytics/drafts/{matchId}`: picks, bans, player roles, and side context.
- Webhook event examples include `lol.live.state`, `lol.live.gold_swing`,
  `lol.live.objective`, `lol.live.kill_update`, `lol.live.tower_destroyed`, and
  `lol.match.completed`.

Pricing and limit claims from the microsite:

- Free testing: 500 requests/month.
- One Game Starter: starts at $10/month for a focused LoL product, commercial
  use, and LoL webhooks.
- Pro: $50/month for higher-volume apps across every game.

These are public documentation claims only; no account-level quota, coverage,
field shape, or latency was validated in this run.

## Selected Match Snapshot Plan

Target selected from the issue body:

```text
Polymarket slug: lol-ly-tsw-2026-07-08
Title: LoL: LYON vs Team Secret Whales (BO5) - Mid-Season Invitational Playoffs
Start: 2026-07-08T03:00:00Z
LoLEsports matchId: 115570934355614587
LoLEsports state at sampling: unstarted
```

Because Cito access was blocked, the raw Cito schedule/live/visual-state rows
could not be collected. The minimum authenticated sample plan once Calvin
provides a Cito key is:

1. `GET /api/v1/lol/schedule/today` and `/api/v1/lol/schedule/upcoming` to map
   Cito match/team IDs to `LYON` and `Team Secret Whales`.
2. During active coverage, `GET /api/v1/lol/live` to discover the current
   `matchId` / `gameId`.
3. `GET /api/v1/lol/matches/{matchId}/coverage` before sampling
   `visual-state`.
4. `GET /api/v1/lol/live/{matchId}/series` and
   `GET /api/v1/lol/live/{gameId}/visual-state` every 10-30 seconds for a short
   live window.
5. If available, `GET /api/v1/lol/analytics/drafts/{matchId}` and
   `GET /api/v1/lol/games/{gameId}/stats` for final picks/bans and post-game
   reconciliation.

Each authenticated response should be stored as raw JSON with `observedAt`,
HTTP status, endpoint, sanitized request headers, and any source timestamp
needed to compute `sourceLatencySec`.

## Polymarket / LoLEsports Mapping Evidence

Cito was blocked, but the selected Polymarket and LoLEsports public mapping
path was probed successfully:

- Full smoke: `docs/source-spike/cito-ly-tsw-polymarket-smoke-2026-07-08.json`
- Mapping sample: `docs/source-spike/cito-ly-tsw-prematch-mapping-2026-07-08.json`
- Observed at: `2026-07-07T19:21:19.963005Z`
- Network requests: 5
- Retries: 0
- Request errors: none

Polymarket Game Winner markets observed:

| Game | Market slug | Condition ID |
|---:|---|---|
| 1 | `lol-ly-tsw-2026-07-08-game1` | `0x43342576493c04880787092fd1f8531506e13e4a2015583eaa497c0a1de56f90` |
| 2 | `lol-ly-tsw-2026-07-08-game2` | `0xa0ac50e4c2323bf54696e9d8abc5759286d27344ea486399cf5dd7faf008eef2` |
| 3 | `lol-ly-tsw-2026-07-08-game3` | `0x9b1a303bd944c6b8e848d0d389dd08cf03854528e91198a859eaa1d840daca10` |
| 4 | `lol-ly-tsw-2026-07-08-game4` | `0xebba19f3f0ae952db0da98314746336fa69d378934cd07570ea4047aba85b704` |

Game 1 orderbook sample:

```text
marketSlug: lol-ly-tsw-2026-07-08-game1
outcome: LYON
tokenId: 75021383113657128951254988248873375148926627720724382363852035551289124917774
bestBid: 0.59
bestAsk: 0.60
bidCount: 22
askCount: 18
sourceTimestamp: 1783452081048
```

Mapping result:

```text
mappingConfidence: 1.0
viable: true
startTimeAligned: true
LYON teamId: 99566405941863385
TSW teamId: 113661839307879869
Game 1 LoLEsports gameId: 115570934355614588
Game 2 LoLEsports gameId: 115570934355614589
Game 3 LoLEsports gameId: 115570934355614590
Game 4 LoLEsports gameId: 115570934355614591
Game 5 LoLEsports gameId: 115570934355614592
```

Boundary: this is a pre-match static mapping and Polymarket orderbook snapshot.
It does not validate Cito live fields or live source latency.

## Field Coverage Verdict

| Field | Cito result in this run | Evidence |
|---|---|---|
| Schedule | Not validated | Blocked by missing API key |
| Team identity | Not validated via Cito | Blocked by missing API key |
| Match/game ID | Not validated via Cito | Blocked by missing API key |
| Final picks | Not validated | Blocked by missing API key |
| Bans | Not validated | Blocked by missing API key |
| Game clock | Not validated | Blocked by missing API key |
| Gold | Not validated | Blocked by missing API key |
| Objectives | Not validated | Blocked by missing API key |
| Paused | Not proven in docs found | Needs authenticated sample or provider confirmation |
| Winner | Not validated | Blocked by missing API key |
| Webhooks | Docs-only | Paid plan claim; no delivery sample |

## Conclusion

```text
usable_as_primary = false
usable_as_backup = false_until_authenticated_live_sample
blocked_reason = missing_cito_api_key
```

Cito remains a low-cost source worth one authenticated live-window test, but it
cannot be accepted as a Phase 1 primary or backup from public docs plus
unauthenticated `401 MISSING_API_KEY` responses.

Minimum unblock request for Calvin:

- Provide a Cito Free Testing / One Game Starter API key through the runtime
  environment only, preferably as `CITO_API_KEY`.
- Confirm whether the account has LoL live and webhook access.
- Re-run during an active match window so `live`, `series`, `visual-state`,
  coverage, draft, and post-game reconciliation endpoints can be sampled.
