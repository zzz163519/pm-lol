# SourceScore

Phase 0 source scoring uses a 100-point scale:

- `officialness` (20)
- `latency` (20)
- `fieldCoverage` (25)
- `reliability` (15)
- `leagueCoverage` (10)
- `costFit` (10)

## Summary

| Source | officialness | latency | fieldCoverage | reliability | leagueCoverage | costFit | Total | Phase 0 Role |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| LoLEsports frontend API | 8/20 | 12/20 | 21/25 | 8/15 | 8/10 | 10/10 | 67 | Current primary spike source |
| PandaScore | 12/20 | 14/20 | 20/25 | 12/15 | 8/10 | 4/10 | 70 | Commercial backup candidate |
| GRID | 20/20 | 18/20 | 24/25 | 14/15 | 9/10 | 2/10 | 87 | Best-quality future upgrade |
| Oracle's Elixir | 10/20 | 0/20 | 14/25 | 13/15 | 8/10 | 10/10 | 55 | Historical data only |
| Cito / unofficial sources | 3/20 | 8/20 | 10/25 | 5/15 | 5/10 | 8/10 | 39 | Not recommended |

## LoLEsports Frontend API

- `officialness` 8/20: It is a Riot/LoLEsports frontend surface but not documented as a stable commercial API.
- `latency` 12/20: Historical `livestats/window` samples include source timestamps, but live `sourceLatencySec` is still unverified.
- `fieldCoverage` 21/25: Existing samples cover match/game IDs, final picks, patch, gold, kills, towers, dragons, barons, inhibitors, and participant state; bans are not covered.
- `reliability` 8/15: The public frontend path worked for the spike, but key/header changes and live stability remain open risks.
- `leagueCoverage` 8/10: LoLEsports should cover major Riot esports leagues, but Phase 0 still needs league-by-league live validation.
- `costFit` 10/10: It is currently free to read and fits the early spike budget.

Decision: Use as the Phase 1 spike primary only after live latency validation; keep production risk marked pending.

## PandaScore

- `officialness` 12/20: It is a commercial esports data provider, not the first-party league data distributor.
- `latency` 14/20: Product docs indicate live frames, but the required live plan needs real-match validation.
- `fieldCoverage` 20/25: Expected LoL frames include game clock, paused/finished/winner, gold, towers, kills, dragons, barons, herald, inhibitors, champions, and players.
- `reliability` 12/15: Commercial API reliability is likely stronger than frontend scraping, subject to plan limits and SLA.
- `leagueCoverage` 8/10: It is expected to cover common pro LoL leagues, but exact Phase 1 league coverage needs account-level confirmation.
- `costFit` 4/10: Free tier is not sufficient for live trading-style validation; paid live access is required.

Decision: Keep as the main commercial backup candidate if LoLEsports live latency or stability fails.

## GRID

- `officialness` 20/20: GRID is the official Riot esports data distribution partner path for commercial live data.
- `latency` 18/20: It is designed for near-real-time live data, pending direct trial or sales confirmation.
- `fieldCoverage` 24/25: It is expected to cover the needed live state and official match context; exact bans/BP shape should be validated in trial.
- `reliability` 14/15: Commercial official feed should have the best operational reliability, subject to contract access.
- `leagueCoverage` 9/10: It likely covers the primary Riot ecosystem, but exact LCK/LPL/LEC/MSI/Worlds access must be confirmed.
- `costFit` 2/10: Cost and access requirements are likely too high for the current spike phase.

Decision: Treat as best-quality future upgrade, not Phase 1 default unless budget and access change.

## Oracle's Elixir

- `officialness` 10/20: It is a trusted community historical dataset, not an official live feed.
- `latency` 0/20: It is not suitable for live ingestion or trading-time decisions.
- `fieldCoverage` 14/25: It is useful for historical teams, players, drafts, and outcomes, but not live gold/objective state.
- `reliability` 13/15: Historical data quality is strong and widely used for analysis workflows.
- `leagueCoverage` 8/10: It has broad historical LoL esports coverage, with caveats around timing and dataset update cadence.
- `costFit` 10/10: It is free and fits model research or offline feature work.

Decision: Use for historical modeling and EGR research only; do not use as a Phase 1 live input.

## Cito / Unofficial Sources

- `officialness` 3/20: It is not an official or primary commercial source for Riot live esports data.
- `latency` 8/20: Live endpoint claims need API-key validation and measured source latency.
- `fieldCoverage` 10/25: Published notes suggest schedules, pick/ban, and stats may exist, but depth is not proven for gold/objective trading inputs.
- `reliability` 5/15: Operational stability and schema stability are uncertain.
- `leagueCoverage` 5/10: League coverage is unclear without account-level testing.
- `costFit` 8/10: It may be inexpensive, but low confidence reduces practical fit.

Decision: Do not recommend for Phase 1 primary or backup until it proves live field depth and reliability.

## Selected Sources

- Primary spike source: LoLEsports frontend API.
- Backup candidate: PandaScore, if paid live access is acceptable.
- Future upgrade: GRID, if official access and cost fit the project.
- Historical-only source: Oracle's Elixir.
- Deprecated for now: Cito / unofficial sources.
