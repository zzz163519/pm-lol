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
| LoLEsports frontend API | 8/20 | 5/20 | 21/25 | 7/15 | 8/10 | 10/10 | 59 | Draft/final-picks, schedule/mapping, terminal winner supplement |
| Polymarket public market data | 10/20 | 10/20 | 18/25 | 8/15 | 6/10 | 10/10 | 62 | Market/orderbook source for conditional data foundation |
| PandaScore | 12/20 | 14/20 | 20/25 | 12/15 | 8/10 | 4/10 | 70 | Commercial backup candidate |
| GRID | 20/20 | 18/20 | 24/25 | 14/15 | 9/10 | 2/10 | 87 | Best-quality future upgrade |
| Oracle's Elixir | 10/20 | 0/20 | 14/25 | 13/15 | 8/10 | 10/10 | 55 | Historical data only |
| Cito | 3/20 | 10/20 | 16/25 | 6/15 | 5/10 | 8/10 | 48 | Conditional primary live-state component |

## LoLEsports Frontend API

- `officialness` 8/20: It is a Riot/LoLEsports frontend surface but not documented as a stable commercial API.
- `latency` 5/20: Active-match numeric frames observed so far were stale; event details also lack a usable source timestamp for end-to-end latency measurement.
- `fieldCoverage` 21/25: Existing samples cover match/game IDs, final picks, patch, gold, kills, towers, dragons, barons, inhibitors, and participant state; bans are not covered.
- `reliability` 7/15: The frontend path worked for schedule, event, picks, and terminal state, but credential/header changes, stale active numeric frames, and schema stability remain open risks.
- `leagueCoverage` 8/10: LoLEsports should cover major Riot esports leagues, but Phase 0 still needs league-by-league live validation.
- `costFit` 10/10: It is currently free to read and fits the early spike budget.

Decision: Use for draft/final-picks, schedule/mapping, and terminal winner
supplementation. Do not use the observed active numeric frames as the primary
live-state path.

## Polymarket Public Market Data

- `officialness` 10/20: Polymarket public web, Gamma, and CLOB endpoints are first-party public surfaces, but the current use depends on undocumented discovery behavior and public endpoint stability.
- `latency` 10/20: CLOB `/book` can be polled without authentication. REST polling is the QuoteRecorder v1 baseline; Market WebSocket push latency is an unvalidated deferred upgrade.
- `fieldCoverage` 18/25: Current retest confirms `Game N Winner` discovery through page HTML event slugs plus Gamma slug detail, and CLOB books expose token-level bids/asks; this covers Phase 1 market metadata and quote polling, but not all live push behavior.
- `reliability` 8/15: Gamma slug detail and CLOB `/book` are viable, but generic Gamma keyword search is unreliable and the current WSL/proxy/direct network path intermittently fails TLS with `SSL_ERROR_SYSCALL`.
- `leagueCoverage` 6/10: Current MSI LoL events were discoverable, but coverage should be validated across LCK, LPL, LEC, MSI, and Worlds as markets appear.
- `costFit` 10/10: Public read-only endpoints require no wallet, no API key, and no paid account for the current spike.

Decision: Use as the conditional Phase 1 market/orderbook source with REST polling and a conservative discovery path:

```text
Polymarket LOL page HTML -> event slug -> Gamma /events/slug/{slug} -> Game [1-5] Winner filter -> CLOB /book
```

Do not treat it as production-safe until network-path stability and collector
retry/error-classification behavior are validated. WebSocket retesting is an
upgrade item, not a Phase 0 blocker.

## PandaScore

- `officialness` 12/20: It is a commercial esports data provider, not the first-party league data distributor.
- `latency` 14/20: Product docs indicate live frames, but the required live plan needs real-match validation.
- `fieldCoverage` 20/25: Expected LoL frames include game clock, paused/finished/winner, gold, towers, kills, dragons, barons, herald, inhibitors, champions, and players.
- `reliability` 12/15: Commercial API reliability is likely stronger than frontend scraping, subject to plan limits and SLA.
- `leagueCoverage` 8/10: It is expected to cover common pro LoL leagues, but exact Phase 1 league coverage needs account-level confirmation.
- `costFit` 4/10: Free tier is not sufficient for live trading-style validation; paid live access is required.

Decision: Keep as the main commercial backup candidate if the Cito + LoLEsports combination fails stability or coverage gates.

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

## Cito

- `officialness` 3/20: It is not an official Riot live esports data source.
- `latency` 10/20: One game showed `sampleAgeSeconds` around 24 seconds. This is a freshness proxy, not measured end-to-end source latency, so the score remains provisional.
- `fieldCoverage` 16/25: CAL-59 evidence covers team identity, gold/goldDiff, objectives, kills, game clock, and game state; draft/final picks still rely on LoLEsports supplementation.
- `reliability` 6/15: Authenticated read access is proven, but CAL-157's later rerun had no active match and does not prove multi-match schema or field stability.
- `leagueCoverage` 5/10: Current evidence is too narrow to establish cross-league coverage.
- `costFit` 8/10: It fits the low-cost spike path, subject to access and usage limits.

Decision: Use as the conditional primary live-state component while retaining
hard gates for multi-match/cross-league stability, authoritative team-side, and
repeated live mapping. The score is independent; do not invent a composite score
for the Cito + LoLEsports combination.

## Selected Sources

- Conditional primary live-state component: Cito.
- Draft/final-picks, schedule/mapping, and terminal winner supplement: LoLEsports frontend API.
- Market/orderbook source: Polymarket public market data via HTML slug discovery, Gamma slug detail, and CLOB REST polling.
- Backup candidate: PandaScore, if paid live access is acceptable.
- Future upgrade: GRID, if official access and cost fit the project.
- Historical-only source: Oracle's Elixir.

These role assignments supersede the earlier LoLEsports-primary/Cito-not-
recommended selection. The earlier selection remains preserved in the decision
log as historical context.
