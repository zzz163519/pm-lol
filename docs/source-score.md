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
| Official-event Twitch HLS | 14/20 | 10/20 | 23/25 | 10/15 | 5/10 | 10/10 | 72 | Validated visual fallback; extraction pending |
| Polymarket public market data | 10/20 | 10/20 | 18/25 | 8/15 | 6/10 | 10/10 | 62 | Market/orderbook source for conditional data foundation |
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

Decision: Use as the current Phase 0 primary spike source. It is not
production-safe until active-match latency, field stability, and league coverage
are validated.

## Official-event Twitch HLS

- `officialness` 14/20: The validated channel carried the official KeSPA event
  feed, while Twitch and the HLS extraction path are third-party transport
  surfaces rather than a Riot structured API.
- `latency` 10/20: Consecutive frames advanced normally and fit the project's
  delay-tolerant semantics, but glass-to-glass source latency has not yet been
  measured against an authoritative clock.
- `fieldCoverage` 23/25: The stable 1080p overlay visibly covers final picks,
  bans, game clock, gold, kills, towers, objective state/events, and player
  rows. Automated inhibitor/Baron extraction still needs an occurrence sample.
- `reliability` 10/15: Public Streamlink-to-HLS capture succeeded without an
  account or API key. Channel naming, event layouts, ads, desk segments, and
  stream availability remain operational risks.
- `leagueCoverage` 5/10: The path works for this KeSPA event and can generalize
  to other broadcast channels, but discovery and overlay geometry are
  tournament-specific until validated.
- `costFit` 10/10: Public read-only capture has no provider fee.

Decision: Keep as the first empirically validated delayed visual fallback.
Do not promote it to automatic normalized input until pick/ban template
matching, numeric OCR, cross-frame agreement, confidence thresholds, and source
latency are measured.

## Polymarket Public Market Data

- `officialness` 10/20: Polymarket public web, Gamma, and CLOB endpoints are first-party public surfaces, but the current use depends on undocumented discovery behavior and public endpoint stability.
- `latency` 10/20: CLOB `/book` can be polled without authentication, but Market WebSocket remains `pending_network_retest`, so push latency is not validated.
- `fieldCoverage` 18/25: Current retest confirms `Game N Winner` discovery through page HTML event slugs plus Gamma slug detail, and CLOB books expose token-level bids/asks; this covers Phase 1 market metadata and quote polling, but not all live push behavior.
- `reliability` 8/15: Gamma slug detail and CLOB `/book` are viable, but generic Gamma keyword search is unreliable and the current WSL/proxy/direct network path intermittently fails TLS with `SSL_ERROR_SYSCALL`.
- `leagueCoverage` 6/10: Current MSI LoL events were discoverable, but coverage should be validated across LCK, LPL, LEC, MSI, and Worlds as markets appear.
- `costFit` 10/10: Public read-only endpoints require no wallet, no API key, and no paid account for the current spike.

Decision: Use for Phase 0 market/orderbook evidence with REST polling and a conservative discovery path:

```text
Polymarket LOL page HTML -> event slug -> Gamma /events/slug/{slug} -> Game [1-5] Winner filter -> CLOB /book
```

Do not treat it as production-safe until WebSocket is retested from a clean
network path and collector retry/error-classification behavior is validated.

## PandaScore

- `officialness` 12/20: It is a commercial esports data provider, not the first-party league data distributor.
- `latency` 14/20: Product docs indicate live frames, but the required live plan needs real-match validation.
- `fieldCoverage` 20/25: Expected LoL frames include game clock, paused/finished/winner, gold, towers, kills, dragons, barons, herald, inhibitors, champions, and players.
- `reliability` 12/15: Commercial API reliability is likely stronger than frontend scraping, subject to plan limits and SLA.
- `leagueCoverage` 8/10: It is expected to cover common pro LoL leagues, but exact Phase 1 league coverage needs account-level confirmation.
- `costFit` 4/10: Free tier is not sufficient for live trading-style validation; paid live access is required.

Decision: Keep as the commercial backup candidate if LoLEsports fails Phase 0.

## GRID

- `officialness` 20/20: GRID is the official Riot esports data distribution partner path for commercial live data.
- `latency` 18/20: It is designed for near-real-time live data, pending direct trial or sales confirmation.
- `fieldCoverage` 24/25: It is expected to cover the needed live state and official match context; exact bans/BP shape should be validated in trial.
- `reliability` 14/15: Commercial official feed should have the best operational reliability, subject to contract access.
- `leagueCoverage` 9/10: It likely covers the primary Riot ecosystem, but exact LCK/LPL/LEC/MSI/Worlds access must be confirmed.
- `costFit` 2/10: Cost and access requirements are likely too high for the current spike phase.

Decision: Treat as the future official upgrade path, subject to budget and access.

## Oracle's Elixir

- `officialness` 10/20: It is a trusted community historical dataset, not an official live feed.
- `latency` 0/20: It is not suitable for live ingestion or trading-time decisions.
- `fieldCoverage` 14/25: It is useful for historical teams, players, drafts, and outcomes, but not live gold/objective state.
- `reliability` 13/15: Historical data quality is strong and widely used for analysis workflows.
- `leagueCoverage` 8/10: It has broad historical LoL esports coverage, with caveats around timing and dataset update cadence.
- `costFit` 10/10: It is free and fits model research or offline feature work.

Decision: Use for historical research only; do not use as a live input.

## Cito / Unofficial Sources

- `officialness` 3/20: It is not an official or primary commercial source for Riot live esports data.
- `latency` 8/20: Live endpoint claims need API-key validation and measured source latency.
- `fieldCoverage` 10/25: Published notes suggest schedules, pick/ban, and stats may exist, but depth is not proven for gold/objective trading inputs.
- `reliability` 5/15: Operational stability and schema stability are uncertain.
- `leagueCoverage` 5/10: League coverage is unclear without account-level testing.
- `costFit` 8/10: It may be inexpensive, but low confidence reduces practical fit.

Decision: Do not recommend for the Phase 1 primary or backup. Existing Cito
captures remain historical comparison evidence and do not override this role.

## Selected Sources

- Primary spike source: official-event Twitch HLS with pure-code template/OCR extraction; two-consecutive-match automated acceptance pending.
- Structured comparison source: LoLEsports frontend API; active-match coverage remains tournament-dependent.
- Market/orderbook source: Polymarket public market data via HTML slug discovery, Gamma slug detail, and CLOB REST polling.
- Backup candidate: PandaScore, if paid live access is acceptable.
- Future upgrade: GRID, if official access and cost fit the project.
- Historical-only source: Oracle's Elixir.
- Not recommended for Phase 1 primary or backup: Cito / unofficial sources.
