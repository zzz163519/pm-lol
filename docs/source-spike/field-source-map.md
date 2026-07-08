# CAL-59 Field Source Map

Read-only Phase 0 mapping for T1 vs G2. This is a source contract, not a
strategy, prediction, signal, wallet integration, or trading permission.

## Field Map

| Field | Primary source | Endpoint | Response path | Notes |
|---|---|---|---|---|
| team identity | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `blueTeam.tag`, `redTeam.tag` | `gameId` must come from `/lol/matches/{matchId}/coverage`, not directly from `/lol/live` matchId. |
| draft/picks | LoLEsports livestats | `GET https://feed.lolesports.com/livestats/v1/window/{gameId}` | `gameMetadata.blueTeamMetadata.participantMetadata[].championId`, `gameMetadata.redTeamMetadata.participantMetadata[].championId` | Use LoLEsports for final champion rows because CITO visual-state did not expose picks in CAL-59. |
| gold | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `blueTeam.gold`, `redTeam.gold` | Raw numeric totals by side. |
| goldDiff | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | derived from `blueTeam.gold - redTeam.gold` | Positive means blue side leads. |
| objectives | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `blueTeam.dragons`, `redTeam.dragons`, `blueTeam.barons`, `redTeam.barons`, `blueTeam.towers`, `redTeam.towers` | CITO visual-state has compact team totals. |
| kills | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `blueTeam.kills`, `redTeam.kills` | Team kill totals. |
| gameClock | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `gameTimeFormatted`, `gameTimeSeconds` | Prefer CITO's explicit clock over LoLEsports frame timestamp. |
| gameState | CITO visual-state | `GET /api/v1/lol/live/{gameId}/visual-state` | `status` | Current CAL-59 value was `provisional`; keep freshness/quality gates separate. |
| winner | LoLEsports eventDetails reconciliation | `GET https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={matchId}` | `event.match.teams[].result.gameWins`, plus `event.match.games[].state` | Winner is available only after terminal reconciliation. Require a completed match and a unique max `gameWins`. |

## Discovery Chain

1. Use CITO `GET /api/v1/lol/schedule/today` or `GET /api/v1/lol/live` to
   discover the T1 vs G2 `matchId`.
2. Use CITO `GET /api/v1/lol/matches/{matchId}/coverage` to resolve the active
   live `gameId`.
3. Use CITO visual-state for in-game numeric fields.
4. Use LoLEsports `getEventDetails` for game ids, team ids, side metadata, and
   winner reconciliation.
5. Use LoLEsports livestats `window/{gameId}` for draft/picks only.

## Current CAL-59 Evidence

- CITO fresh-key retest: `docs/source-spike/cito-t1-g2-field-probe-20260708T062648799Z.json`
- LoLEsports livestats retest: `docs/source-spike/lolesports-t1-g2-livestats-probe-20260708T061938601Z.json`
- Dual-source/winner reconciliation retest: `docs/source-spike/field-source-map-probe-20260708T065350407Z.json`

## Winner Reconciliation Status

The `20260708T065350407Z` retest observed LoLEsports `getEventDetails` for T1 vs
G2 after Game 1 completed. `event.match.games[]` had one `completed` game and
`event.match.teams[].result.gameWins` produced a unique winner:

- G2: `gameWins=1`
- T1: `gameWins=0`

The same retest also resolved all mapped fields through the split script:
draft/picks came from LoLEsports livestats, while team identity, gold,
goldDiff, objectives, kills, gameClock, and gameState came from CITO
visual-state. The CITO sample reported `gameState=stale`, so downstream live
loops still need a freshness gate separate from field presence.
