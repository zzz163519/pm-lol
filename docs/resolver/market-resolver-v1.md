# MarketResolver v1

Scope: Phase 1 mapping of Polymarket LoL `Game N Winner` markets to LoLEsports
match/game/team-side records. This is read-only evidence plumbing only; it does
not create strategy, prediction, signal, wallet, broker, or order execution
logic.

## Contract

Inputs:

- Polymarket `Market`: `market_id`, `condition_id`, `slug`, `title`,
  `outcomes`, `token_ids`, optional event slug/start metadata, and
  `market_type`.
- LoLEsports `Match`: `match_id`, league, start time, team IDs, team names.
- LoLEsports `Game`: `game_id`, `game_number`, blue team ID, red team ID.

Output:

- `resolve_market_attempt(...)` returns a `MarketResolutionAttempt` for every
  candidate.
- `resolve_market_to_game(...)` remains the compatibility wrapper and returns
  `ResolvedMarket | None`.
- `resolve_pending_markets(...)` writes both mapped and skipped attempts to
  SQLite `resolved_markets`.

Structured fields preserved in the attempt/artifact:

- `marketSlug`
- `matchId`
- `gameId`
- `gameNumber`
- `tokenOutcome`
- `tokenId`
- `teamSide`
- `teamId`
- `mappingConfidence`
- `skipReason`

## Hard Gate

`mappingConfidence >= 0.90` is required for a mapped result. Anything below the
threshold is skipped and recorded; resolver callers must not force a mapping.

Skip reasons:

- `non_game_winner`
- `ambiguous_game_number`
- `ambiguous_token_outcomes`
- `team_mismatch`
- `time_mismatch`
- `team_side_unknown`
- `insufficient_market` for artifact-level evidence shortages

Time matching uses a 30-minute tolerance when both Polymarket and LoLEsports
start times are present. Storage-level resolution treats missing start time as
unsafe: a single otherwise valid candidate is skipped as `missing_start_time`,
and multiple otherwise valid candidates are skipped as
`ambiguous_match_candidates`.

Team matching requires each side to clear the hard gate. A high average cannot
hide one weak side. Canonical substring matches are capped below the hard gate,
so `KT Rolster` cannot pass as `KT Rolster Challengers`, `Academy`, or `Youth`
only because one name contains the other.

## Current Evidence

Structured artifact:

- `docs/source-spike/cal-68-market-resolver-v1-artifact.json`

Source samples:

- BLG vs HLE, MSI, 2026-07-09: mapped, `mappingConfidence=1.0`.
- LYON vs Team Secret Whales, MSI, 2026-07-08: mapped,
  `mappingConfidence=1.0`.
- BLG vs T1, MSI, 2026-07-04: skipped,
  `mapping_confidence_below_0.90`.

Current availability status is `insufficient_high_confidence_markets`: only two
Current availability status is `insufficient_market`: only two high-confidence
same-event samples are available in the checked-in spike artifacts. The
low-confidence BLG/T1 fixture is retained as a regression case for skip behavior
rather than upgraded by hand.
