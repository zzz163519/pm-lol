# CAL-59 LoLEsports Livestats Field Probe

Window: `2026-07-08T06:19:38.601Z` to `2026-07-08T06:19:44.808Z` UTC.

Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.

## Target

- matchId: `115570934355614581`
- gameId: `115570934355614582`
- event state: `None`

## Endpoint Status

- schedule: `200` / `None`
- eventDetails: `200` / `None`
- window: `200` / `None`
- details: `200` / `None`

## Freshness

- frame timestamp: `2026-07-08T05:52:48.791Z`
- frame age: `1616.017` seconds
- freshness threshold: `120` seconds

## Field Coverage

| Field | Status | Sample |
|---|---|---|
| `teamIdentity` | `present` | `[{"code": "G2", "id": "98767991926151025", "name": "G2 Esports"}, {"code": "T1", "id": "98767991853197861", "name": "T1"}]` |
| `gold` | `present` | `{"blue": 0, "red": 0}; goldDiff=0` |
| `objectives` | `present` | `{"blue": {"barons": 0, "dragons": [], "inhibitors": 0, "towers": 0}, "red": {"barons": 0, "dragons": [], "inhibitors": 0, "towers": 0}}` |
| `kills` | `present` | `{"blue": 0, "red": 0}` |
| `draftPicks` | `present` | `{"blue": ["Vayne", "JarvanIV", "Anivia", "Ezreal", "Leona"], "red": ["Renekton", "Nocturne", "Cassiopeia", "Ziggs", "Camille"]}` |
| `gameState` | `present` | `"in_game"` |
| `gameClock` | `derived_from_frame_timestamp` | `"2026-07-08T05:52:48.791Z"` |
| `winner` | `missing` | `"not_exposed_in_livestats_frame"` |

## Conclusion

LoLEsports livestats partially supplements Cito, but these fields remain missing: winner. Latest livestats frame was stale at 1616.017s old, so treat this as schema/field evidence, not fresh live state.

Raw JSON: `docs/source-spike/lolesports-t1-g2-livestats-probe-20260708T061938601Z.json`
