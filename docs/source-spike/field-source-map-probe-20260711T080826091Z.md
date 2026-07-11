# CAL-59 Dual Source Field Probe

Window: `2026-07-11T08:08:26.091Z` to `2026-07-11T08:08:39.440Z` UTC.

Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.

## Target

- matchId: `115570934355614599`
- gameId: `115570934355614600`

## Field Coverage

| Field | Status | Source | Path | Sample |
|---|---|---|---|---|
| `teamIdentity` | `missing` | `cito_visual_state` | `blueTeam.tag, redTeam.tag` | `{"blue": null, "red": null}` |
| `gold` | `missing` | `cito_visual_state` | `blueTeam.gold, redTeam.gold` | `{"blue": null, "red": null}` |
| `goldDiff` | `missing` | `derived_from_cito_visual_state` | `blueTeam.gold - redTeam.gold` | `null` |
| `objectives` | `missing` | `cito_visual_state` | `blueTeam.{dragons,barons,towers}, redTeam.{dragons,barons,towers}` | `{"blue": {"barons": null, "dragons": null, "towers": null}, "red": {"barons": null, "dragons": null, "towers": null}}` |
| `kills` | `missing` | `cito_visual_state` | `blueTeam.kills, redTeam.kills` | `{"blue": null, "red": null}` |
| `gameClock` | `missing` | `cito_visual_state` | `gameTimeFormatted, gameTimeSeconds` | `{"formatted": null, "seconds": null}` |
| `gameState` | `present` | `cito_visual_state` | `status` | `"not_ready"` |
| `draftPicks` | `missing` | `lolesports_livestats` | `gameMetadata.{blue,red}TeamMetadata.participantMetadata[].championId` | `{"blue": [], "red": []}` |
| `winner` | `pending` | `lolesports_event_details` | `event.match.teams[].result.gameWins with event.match.games[].state` | `null` |

## Winner Reconciliation

- status: `pending`
- completedGameCount: `0`
- teamResults: `[{"code": "LYON", "gameWins": 0, "id": "99566405941863385", "name": "LYON"}, {"code": "HLE", "gameWins": 0, "id": "100205573496804586", "name": "Hanwha Life Esports"}]`

## Conclusion

Dual-source mapping is wired, but unresolved fields remain: teamIdentity, gold, goldDiff, objectives, kills, gameClock, draftPicks, winner.

Raw JSON: `docs/source-spike/field-source-map-probe-20260711T080826091Z.json`
