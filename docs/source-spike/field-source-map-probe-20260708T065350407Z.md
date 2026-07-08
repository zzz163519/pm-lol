# CAL-59 Dual Source Field Probe

Window: `2026-07-08T06:53:50.407Z` to `2026-07-08T06:53:59.044Z` UTC.

Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.

## Target

- matchId: `115570934355614581`
- gameId: `115570934355614582`

## Field Coverage

| Field | Status | Source | Path | Sample |
|---|---|---|---|---|
| `teamIdentity` | `present` | `cito_visual_state` | `blueTeam.tag, redTeam.tag` | `{"blue": "G2", "red": "T1"}` |
| `gold` | `present` | `cito_visual_state` | `blueTeam.gold, redTeam.gold` | `{"blue": 89400, "red": 84900}` |
| `goldDiff` | `present` | `derived_from_cito_visual_state` | `blueTeam.gold - redTeam.gold` | `4500` |
| `objectives` | `present` | `cito_visual_state` | `blueTeam.{dragons,barons,towers}, redTeam.{dragons,barons,towers}` | `{"blue": {"barons": 0, "dragons": 3, "towers": 7}, "red": {"barons": 1, "dragons": 4, "towers": 6}}` |
| `kills` | `present` | `cito_visual_state` | `blueTeam.kills, redTeam.kills` | `{"blue": 23, "red": 20}` |
| `gameClock` | `present` | `cito_visual_state` | `gameTimeFormatted, gameTimeSeconds` | `{"formatted": "45:21", "seconds": 2721}` |
| `gameState` | `present` | `cito_visual_state` | `status` | `"stale"` |
| `draftPicks` | `present` | `lolesports_livestats` | `gameMetadata.{blue,red}TeamMetadata.participantMetadata[].championId` | `{"blue": ["Vayne", "JarvanIV", "Anivia", "Ezreal", "Leona"], "red": ["Renekton", "Nocturne", "Cassiopeia", "Ziggs", "Camille"]}` |
| `winner` | `present` | `lolesports_event_details` | `event.match.teams[].result.gameWins with event.match.games[].state` | `{"code": "G2", "gameWins": 1, "id": "98767991926151025", "name": "G2 Esports"}` |

## Winner Reconciliation

- status: `present`
- completedGameCount: `1`
- teamResults: `[{"code": "G2", "gameWins": 1, "id": "98767991926151025", "name": "G2 Esports"}, {"code": "T1", "gameWins": 0, "id": "98767991853197861", "name": "T1"}]`

## Conclusion

Dual-source mapping resolved every tracked field, including winner reconciliation.

Raw JSON: `docs/source-spike/field-source-map-probe-20260708T065350407Z.json`
