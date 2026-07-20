# LoLEsports Frontend API Spike

> Date: 2026-06-15
> Status: usable for historical/live-state spike; live latency still needs real live-match validation

## Summary

LoLEsports frontend APIs can provide the main data chain needed for Phase 0:

```text
schedule -> matchId -> eventDetails -> gameId -> livestats window/details
```

This source is not an official public developer API. It uses the same frontend API key used by the LoLEsports web app. Treat it as a high-value but higher-operational-risk source.

## Tested Endpoints

### Schedule / Metadata

```text
GET https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US
GET https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US
GET https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={matchId}
GET https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US&id={teamId}
```

Required header:

```text
x-api-key: ${LOLESPORTS_API_KEY}
```

Inject `LOLESPORTS_API_KEY` from the runtime environment. Do not commit the
credential or write it into source-spike artifacts.

Without the frontend API key, `persisted/gw/*` returns:

```json
{"message":"Forbidden"}
```

### Live Stats

```text
GET https://feed.lolesports.com/livestats/v1/window/{gameId}
GET https://feed.lolesports.com/livestats/v1/window/{gameId}?startingTime={RFC3339}
GET https://feed.lolesports.com/livestats/v1/details/{gameId}
GET https://feed.lolesports.com/livestats/v1/details/{gameId}?startingTime={RFC3339}
```

`startingTime` should use stable whole-second timestamps, for example:

```text
2026-06-14T06:42:30.000Z
```

Millisecond timestamps copied directly from frames can return `400 Bad Request` in some cases.

## Sample Match

Tested match:

```text
League: LCK
Match: T1 vs GEN
Match ID: 115548128963037587
Game 1 ID: 115548128963037588
Date: 2026-06-14
```

Saved samples:

```text
docs/source-spike/lolesports-event-t1-gen-sample.json
docs/source-spike/lolesports-window-t1-gen-g1-15m-sample.json
docs/source-spike/lolesports-details-t1-gen-g1-15m-sample.json
```

## Field Coverage

### Match / Game Mapping

`getSchedule` provides:

- `startTime`
- `state`
- `league.slug`
- `match.id`
- `match.teams[].name`
- `match.teams[].code`
- `match.strategy.type`
- `match.strategy.count`

`getEventDetails` provides:

- `event.id`
- `league.id`
- `league.slug`
- `match.teams[].id`
- `match.teams[].name`
- `match.teams[].code`
- `match.games[].number`
- `match.games[].id`
- `match.games[].state`
- `match.games[].teams[].id`
- `match.games[].teams[].side`
- VOD metadata

This is enough for:

```text
Polymarket title -> league/team names -> matchId -> gameNumber -> gameId -> blue/red side
```

### Window State

`livestats/v1/window/{gameId}` provides:

- `esportsGameId`
- `esportsMatchId`
- `gameMetadata.patchVersion`
- blue/red `esportsTeamId`
- participant `summonerName`
- participant `championId`
- participant `role`
- frame `rfc460Timestamp`
- frame `gameState`
- blue/red `totalGold`
- blue/red `inhibitors`
- blue/red `towers`
- blue/red `barons`
- blue/red `totalKills`
- blue/red `dragons`
- participant `level`
- participant `kills`
- participant `deaths`
- participant `assists`
- participant `creepScore`
- participant `currentHealth`
- participant `maxHealth`

At 15-minute sample for T1 vs GEN game 1:

```text
timestamp: 2026-06-14T06:42:30.007Z
blueGold: 26066
redGold: 28132
goldDiff: -2066
blueKills: 5
redKills: 8
blueTowers: 0
redTowers: 1
blueDragons: []
redDragons: [infernal, mountain]
blueBarons: 0
redBarons: 0
state: in_game
```

### Details State

`livestats/v1/details/{gameId}` provides per-participant detail:

- level
- totalGoldEarned
- creepScore
- kills/deaths/assists
- championDamageShare
- wardsPlaced
- wardsDestroyed
- attackDamage
- abilityPower
- armor / magicResistance
- items
- perks
- abilities

This is useful for richer paper-trade review but is not required for the first edge/capacity signal.

## Time / Game Clock Handling

The API does not expose a direct `gameClock` field in the tested `window` response.

Practical first version:

```text
gameClockSec = frame.rfc460Timestamp - first in_game zero-state frame timestamp
```

This worked well enough for historical sampling at 1, 3, 5, 10, 15, 20, 25, and 30 minutes.

Still required:

- Validate this calculation during a live match.
- Check whether pauses distort timestamp-based game clock.
- Check whether `gameState` exposes enough pause/remake state.

## Known Gaps

- Ban phase data was not found in tested `getEventDetails` or `livestats` responses.
- Explicit `gameClock` was not found; must be derived unless another endpoint is discovered.
- Live latency is not validated yet because no match was live during the test window.
- Frontend API key may change without notice.
- This is a frontend/private API surface, not a contractual data product.

## Phase 0 Judgment

Current judgment:

```text
candidate_primary_for_spike = true
candidate_primary_for_production = risky_until_live_validation
```

This source appears strong enough to proceed with a dedicated Phase 0 connector spike before paying for PandaScore / GRID.

It does not fully close Phase 0 until a live match test confirms:

- latest frame updates during live game
- source latency
- stable polling interval
- no missing frames during pause / side swap / between games
- coverage for LCK, LPL, LEC, MSI/Worlds

## Next Test

Use the next scheduled match:

```text
2026-06-15T15:00:00Z
EMEA Masters
GL vs SLY
matchId: 116634566264113564
```

Live test checklist:

- Pull `getEventDetails` before match start and confirm game IDs appear.
- Poll `getEventDetails` during BP / game start to detect when game IDs become available.
- Poll `window/{gameId}` every 5-10 seconds once game starts.
- Record observedAt locally and compare with `rfc460Timestamp`.
- Save one raw frame every minute.
- Confirm whether champion picks appear before first in-game frame.
- Confirm whether bans appear anywhere.
- Confirm whether pauses can be detected.
