# Conditional Phase 1 Data Foundation Schema

This schema defines the Conditional Phase 1 Data Foundation for Polymarket LoL
`Game N Winner` markets. It is intentionally limited to market discovery, quote
capture, match/game mapping, final draft state, live game state snapshots, and
collector observability. It is not full Phase 1 and must not be used to start
strategy, edge, signal, paper trading, wallet, private key, or order work.

## Conventions

- Database: SQLite.
- Time fields use RFC3339 UTC text unless the source only provides epoch millis.
- JSON-like fields are stored as `TEXT` containing JSON.
- Monetary/probability/price values use `REAL`; Polymarket token IDs remain `TEXT`
  because they exceed integer ranges.
- Every table has a source/confidence trail where applicable.
- `mapping_confidence < 0.90` is stored but must not enter any downstream
  strategy / edge / signal layer.
- Phase 1 market scope is `market_type = 'game_winner'` only.
- `source_status` values should be canonical where present:
  `ok`, `partial`, `missing_field`, `stale`, `rate_limited`, `auth_required`,
  `network_error`, `parse_error`, `skipped_low_confidence`.
- Schema-bearing collector outputs should include `source_schema_version`.
- Repeated collector executions should be grouped by `collector_run_id` and
  summarized in `collector_runs`.

## 1. `markets`

Polymarket market metadata from Gamma/CLOB discovery.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `market_id` | TEXT | no | Polymarket Gamma `selectedMarket.id` | Primary key. |
| `condition_id` | TEXT | no | Polymarket Gamma `conditionId` | Unique. |
| `question_id` | TEXT | yes | Polymarket Gamma `questionID` | Optional Gamma field. |
| `event_id` | TEXT | yes | Polymarket Gamma event `id` | Event grouping. |
| `event_slug` | TEXT | yes | Polymarket Gamma event `slug` | Example: `lol-ktc-sgw-2026-06-15`. |
| `slug` | TEXT | no | Polymarket Gamma market `slug` | Example includes game number. |
| `title` | TEXT | no | Polymarket Gamma market `question` | Human-readable market title. |
| `market_type` | TEXT | no | Parser/resolver | Phase 1 accepts `game_winner`; unknown markets are skipped downstream. |
| `outcomes_json` | TEXT | no | Polymarket Gamma `outcomes` | JSON array of outcome names. |
| `token_ids_json` | TEXT | no | Polymarket Gamma `clobTokenIds` | JSON array aligned with outcomes. |
| `yes_token_id` | TEXT | yes | Derived from token IDs | First outcome token when binary direction is known. |
| `no_token_id` | TEXT | yes | Derived from token IDs | Second outcome token when binary direction is known. |
| `volume` | REAL | yes | Polymarket Gamma market/event `volume` | Market volume preferred; event volume optional fallback. |
| `liquidity` | REAL | yes | Polymarket Gamma `liquidity` | Current liquidity. |
| `active` | INTEGER | no | Polymarket Gamma `active` | Boolean stored as 0/1. |
| `closed` | INTEGER | no | Polymarket Gamma `closed` | Boolean stored as 0/1. |
| `start_time` | TEXT | yes | Polymarket event `startDate` | Event start. |
| `end_time` | TEXT | yes | Polymarket event `endDate` | Event end. |
| `raw_json` | TEXT | no | Polymarket API | Original market/event payload. |
| `source` | TEXT | no | Collector | Example: `polymarket_gamma`. |
| `confidence` | REAL | no | Collector | Metadata parse confidence; default `1.0` for valid payloads. |
| `created_at` | TEXT | no | System | Insert time. |
| `updated_at` | TEXT | no | System | Last metadata refresh time. |

Indexes:

- `UNIQUE(condition_id)`
- `INDEX(slug)`
- `INDEX(active, closed)`

## 2. `resolved_markets`

Resolver output mapping a Polymarket market to a LoLEsports match/game/team side.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `resolved_market_id` | TEXT | no | Resolver | Primary key; stable derived ID is acceptable. |
| `market_id` | TEXT | no | `markets.market_id` | Foreign key. |
| `condition_id` | TEXT | no | `markets.condition_id` | Duplicated for quote joins. |
| `yes_token_id` | TEXT | no | `markets.token_ids_json` | Token for first mapped outcome. |
| `no_token_id` | TEXT | no | `markets.token_ids_json` | Token for second mapped outcome. |
| `league` | TEXT | yes | LoLEsports schedule/event | Example: `LCK`; nullable until schedule is resolved. |
| `match_id` | TEXT | no | LoLEsports event `id` | Foreign key to `matches.match_id`. |
| `game_id` | TEXT | no | LoLEsports game `id` | Foreign key to `games.game_id`. |
| `game_number` | INTEGER | no | Polymarket title/slug + LoLEsports event | Hard gate: must be clear. |
| `team_a_id` | TEXT | yes | LoLEsports team ID | Polymarket outcome A mapped to LoLEsports. |
| `team_b_id` | TEXT | yes | LoLEsports team ID | Polymarket outcome B mapped to LoLEsports. |
| `team_a_name` | TEXT | no | Polymarket/LoLEsports | Normalized display name. |
| `team_b_name` | TEXT | no | Polymarket/LoLEsports | Normalized display name. |
| `blue_team_id` | TEXT | no | LoLEsports game side | Hard gate: side must be clear. |
| `red_team_id` | TEXT | no | LoLEsports game side | Hard gate: side must be clear. |
| `blue_team_name` | TEXT | yes | LoLEsports schedule/event | Display/debug. |
| `red_team_name` | TEXT | yes | LoLEsports schedule/event | Display/debug. |
| `market_type` | TEXT | no | Resolver | Must be `game_winner` for Phase 1. |
| `mapping_confidence` | REAL | no | Resolver | Hard gate: `< 0.90` records only. |
| `market_status` | TEXT | no | Polymarket + resolver | Example: `active`, `closed`, `resolved`, `skipped_low_confidence`. |
| `skip_reason` | TEXT | yes | Resolver | Required when skipped. |
| `raw_mapping_json` | TEXT | no | Resolver | Evidence: matched names, aliases, scores. |
| `source` | TEXT | no | Resolver | Example: `market_match_resolver`. |
| `confidence` | REAL | no | Resolver | Same as `mapping_confidence` unless a broader confidence is needed. |
| `created_at` | TEXT | no | System | Insert time. |
| `updated_at` | TEXT | no | System | Last resolver refresh time. |

Indexes:

- `UNIQUE(market_id, game_id)`
- `INDEX(condition_id)`
- `INDEX(match_id, game_number)`
- `INDEX(mapping_confidence)`

## 3. `quotes`

Polymarket CLOB orderbook snapshots by token.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `quote_id` | TEXT | no | Collector | Primary key; can be hash of token/time. |
| `condition_id` | TEXT | no | Polymarket orderbook `market` | Links to market condition. |
| `token_id` | TEXT | no | Polymarket orderbook `asset_id` | Outcome token ID. |
| `best_bid` | REAL | yes | Polymarket orderbook `bids` | Highest bid; null if no bids. |
| `best_ask` | REAL | yes | Polymarket orderbook `asks` | Lowest ask; null if no asks. |
| `spread` | REAL | yes | Derived | `best_ask - best_bid` when both exist. |
| `bid_depth` | REAL | no | Derived from bids | Sum of bid sizes in snapshot. |
| `ask_depth` | REAL | no | Derived from asks | Sum of ask sizes in snapshot. |
| `bids_json` | TEXT | no | Polymarket orderbook `bids` | Full ladder. |
| `asks_json` | TEXT | no | Polymarket orderbook `asks` | Full ladder. |
| `last_trade_price` | REAL | yes | Polymarket orderbook `last_trade_price` | Optional. |
| `min_order_size` | REAL | yes | Polymarket orderbook `min_order_size` | Optional. |
| `tick_size` | REAL | yes | Polymarket orderbook `tick_size` | Optional. |
| `neg_risk` | INTEGER | yes | Polymarket orderbook `neg_risk` | Boolean stored as 0/1. |
| `source_timestamp_ms` | INTEGER | yes | Polymarket orderbook `timestamp` | Epoch millis from CLOB. |
| `observed_at` | TEXT | no | System | Local receipt time. |
| `source_latency_sec` | REAL | yes | Derived | `observed_at - source_timestamp_ms` when meaningful. |
| `raw_json` | TEXT | no | Polymarket CLOB | Original orderbook object. |
| `source` | TEXT | no | Collector | Example: `polymarket_clob_rest`. |
| `confidence` | REAL | no | Collector | Default `1.0` for valid snapshots. |
| `created_at` | TEXT | no | System | Insert time. |

Indexes:

- `INDEX(condition_id, observed_at)`
- `INDEX(token_id, observed_at)`

QuoteRecorder v1 compatibility note:

- CAL-67 / PR #3 owns the authoritative QuoteRecorder v1 `quotes` snapshot
  contract and should remain the source of truth for quote-table wording.
- Within Conditional Phase 1 docs, `quotes.source_status` should be treated as
  the canonical per-snapshot status field when QuoteRecorder v1 is layered in.
- Snapshot lineage should carry `source_schema_version` plus either
  `collector_run_id` through `collector_runs` or an adjacent `source_events`
  table in a later follow-up, without widening the current CAL-70-preceding
  data-foundation boundary.

## 4. `matches`

LoLEsports match-level schedule/event data.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `match_id` | TEXT | no | LoLEsports event `id` | Primary key. |
| `league` | TEXT | yes | LoLEsports league `name` or `slug` | Example: `LCK`. |
| `league_id` | TEXT | yes | LoLEsports league `id` | Optional. |
| `league_slug` | TEXT | yes | LoLEsports league `slug` | Optional. |
| `team_a_id` | TEXT | no | LoLEsports match teams[0].id | First scheduled team. |
| `team_a_name` | TEXT | no | LoLEsports match teams[0].name | Display name. |
| `team_a_code` | TEXT | yes | LoLEsports match teams[0].code | Example: `T1`. |
| `team_b_id` | TEXT | no | LoLEsports match teams[1].id | Second scheduled team. |
| `team_b_name` | TEXT | no | LoLEsports match teams[1].name | Display name. |
| `team_b_code` | TEXT | yes | LoLEsports match teams[1].code | Example: `GEN`. |
| `start_time` | TEXT | yes | LoLEsports schedule/event | Scheduled start if available. |
| `state` | TEXT | yes | LoLEsports schedule/event | Scheduled/live/completed where available. |
| `strategy_type` | TEXT | yes | Project config | Phase 1 classification; no strategy execution. |
| `strategy_count` | INTEGER | no | Project config/runtime | Default `0`; count of associated strategy candidates later. |
| `raw_json` | TEXT | no | LoLEsports API | Original event/schedule payload. |
| `source` | TEXT | no | Collector | Example: `lolesports_event_details`. |
| `confidence` | REAL | no | Collector | Default `1.0` for valid schedule/event data. |
| `created_at` | TEXT | no | System | Insert time. |
| `updated_at` | TEXT | no | System | Last refresh time. |

Indexes:

- `INDEX(league, start_time)`
- `INDEX(team_a_id, team_b_id)`

## 5. `games`

LoLEsports game-level mapping, including blue/red side.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `game_id` | TEXT | no | LoLEsports game `id` | Primary key. |
| `match_id` | TEXT | no | `matches.match_id` | Foreign key. |
| `game_number` | INTEGER | no | LoLEsports game `number` | Required for market mapping. |
| `blue_team_id` | TEXT | no | LoLEsports game teams side | Team with `side = blue`. |
| `red_team_id` | TEXT | no | LoLEsports game teams side | Team with `side = red`. |
| `state` | TEXT | no | LoLEsports game `state` / livestats `gameState` | Example: `in_game`, `completed`. |
| `start_time` | TEXT | yes | LoLEsports VOD/live metadata | Optional. |
| `patch` | TEXT | yes | LoLEsports livestats `patchVersion` | Example: `16.11.781.1789`. |
| `raw_json` | TEXT | no | LoLEsports API | Original game payload. |
| `source` | TEXT | no | Collector | Example: `lolesports_event_details`. |
| `confidence` | REAL | no | Collector | Default `1.0` when side is clear. |
| `created_at` | TEXT | no | System | Insert time. |
| `updated_at` | TEXT | no | System | Last refresh time. |

Indexes:

- `UNIQUE(match_id, game_number)`
- `INDEX(blue_team_id, red_team_id)`
- `INDEX(state)`

## 6. `game_state_snapshots`

Live game state snapshots from LoLEsports livestats/window or equivalent source.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `snapshot_id` | TEXT | no | Collector | Primary key; can be hash of game/time. |
| `game_id` | TEXT | no | LoLEsports livestats game ID | Foreign key to `games.game_id`. |
| `game_clock` | REAL | yes | Derived | Seconds since game start when derivable. |
| `observed_at` | TEXT | no | System | Local receipt time. |
| `source_timestamp` | TEXT | no | LoLEsports `rfc460Timestamp` | Source frame time. |
| `source_latency_sec` | REAL | yes | Derived | Local receipt minus source timestamp. |
| `game_state` | TEXT | no | LoLEsports `gameState` | Example: `in_game`. |
| `blue_gold` | INTEGER | no | LoLEsports blueTeam `totalGold` | Total team gold. |
| `red_gold` | INTEGER | no | LoLEsports redTeam `totalGold` | Total team gold. |
| `gold_diff` | INTEGER | no | Derived | `blue_gold - red_gold`. |
| `blue_towers` | INTEGER | no | LoLEsports blueTeam `towers` | Tower count. |
| `red_towers` | INTEGER | no | LoLEsports redTeam `towers` | Tower count. |
| `blue_dragons` | INTEGER | no | Derived from blueTeam `dragons` | Count. |
| `red_dragons` | INTEGER | no | Derived from redTeam `dragons` | Count. |
| `blue_dragons_json` | TEXT | no | LoLEsports blueTeam `dragons` | Dragon types. |
| `red_dragons_json` | TEXT | no | LoLEsports redTeam `dragons` | Dragon types. |
| `first_dragon_team` | TEXT | yes | Derived | `blue`, `red`, or null if unknown. |
| `blue_barons` | INTEGER | no | LoLEsports blueTeam `barons` | Baron count. |
| `red_barons` | INTEGER | no | LoLEsports redTeam `barons` | Baron count. |
| `baron_status` | TEXT | yes | Derived/source | Current baron state if available. |
| `elder_status` | TEXT | yes | Derived/source | Current elder state if available. |
| `blue_kills` | INTEGER | no | LoLEsports blueTeam `totalKills` | Team kills. |
| `red_kills` | INTEGER | no | LoLEsports redTeam `totalKills` | Team kills. |
| `blue_inhibitors` | INTEGER | yes | LoLEsports blueTeam `inhibitors` | Nullable for sources without this field. |
| `red_inhibitors` | INTEGER | yes | LoLEsports redTeam `inhibitors` | Nullable for sources without this field. |
| `paused` | INTEGER | yes | Derived/source | Nullable unknown. Do not default to `0` unless source explicitly reports not paused. |
| `finished` | INTEGER | no | Derived/source | Boolean stored as 0/1. |
| `winner` | TEXT | yes | Source/derived | `blue`, `red`, team ID, or null while live. |
| `participants_json` | TEXT | no | LoLEsports frame participants | Per-player gold/level/CS/KDA/health. |
| `source_status` | TEXT | no | Collector | Canonical collector status, e.g. `ok`, `stale`, `missing_field`, `parse_error`. |
| `source_schema_version` | TEXT | yes | Collector | Version of the parser/output contract. |
| `collector_run_id` | TEXT | yes | `collector_runs.run_id` | Groups snapshots from one polling run. |
| `raw_json` | TEXT | no | LoLEsports API | Original frame/window payload. |
| `source` | TEXT | no | Collector | Example: `lolesports_livestats_window`. |
| `confidence` | REAL | no | Collector | Lower when latency/state anomalies are detected. |
| `created_at` | TEXT | no | System | Insert time. |

Indexes:

- `UNIQUE(game_id, source_timestamp)`
- `INDEX(game_id, observed_at)`

## 7. `draft_snapshots`

Final or in-progress draft state from LoLEsports metadata or equivalent source.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `draft_snapshot_id` | TEXT | no | Collector | Primary key; can be hash of game/team/participant. |
| `match_id` | TEXT | no | LoLEsports match ID | Foreign key to `matches.match_id`. |
| `game_id` | TEXT | no | LoLEsports game ID | Foreign key to `games.game_id`. |
| `patch` | TEXT | yes | LoLEsports `patchVersion` | Patch string. |
| `team_id` | TEXT | no | LoLEsports team metadata | Team for this row. |
| `team_side` | TEXT | no | LoLEsports metadata | `blue` or `red`. |
| `participant_id` | INTEGER | no | LoLEsports participant metadata | In-game participant ID. |
| `esports_player_id` | TEXT | yes | LoLEsports participant metadata | Player ID. |
| `champion_id` | TEXT | no | LoLEsports participant metadata | Example: `Vayne`. |
| `role` | TEXT | no | LoLEsports participant metadata | top/jungle/mid/bottom/support. |
| `summoner_name` | TEXT | no | LoLEsports participant metadata | Example: `T1 Faker`. |
| `blue_team_id` | TEXT | no | LoLEsports metadata | Snapshot-level convenience field. |
| `red_team_id` | TEXT | no | LoLEsports metadata | Snapshot-level convenience field. |
| `blue_champions_json` | TEXT | no | Derived | Five champion IDs when complete, otherwise current list. |
| `red_champions_json` | TEXT | no | Derived | Five champion IDs when complete, otherwise current list. |
| `bans_json` | TEXT | yes | Source/derived | Nullable because current LoLEsports samples do not expose bans. |
| `draft_complete` | INTEGER | no | Derived | Boolean stored as 0/1; data completeness flag only, not a signal gate. |
| `observed_at` | TEXT | no | System | Local receipt time. |
| `source_timestamp` | TEXT | yes | Source | Nullable when metadata has no timestamp. |
| `source_latency_sec` | REAL | yes | Derived | Nullable when source timestamp is absent. |
| `raw_json` | TEXT | no | LoLEsports API | Original participant/team metadata. |
| `source` | TEXT | no | Collector | Example: `lolesports_livestats_window_metadata`. |
| `confidence` | REAL | no | Collector | Lower if champion/side is missing or non-standard. |
| `created_at` | TEXT | no | System | Insert time. |

Indexes:

- `UNIQUE(game_id, participant_id, observed_at)`
- `INDEX(match_id, game_id)`
- `INDEX(game_id, draft_complete)`
- `INDEX(team_id, team_side)`

## Connector Coverage

- `MarketResolver` output lands in `resolved_markets`, with source market fields in
  `markets`.
- `LiveGameStateConnector` output lands in `game_state_snapshots`.
- `DraftStateConnector` output lands in `draft_snapshots`, with game side context in
  `games`.
- No `FairProbabilityEngine`, `EdgeCapacityCalculator`, signal engine, paper
  broker, wallet, private key, or order component is part of Conditional Phase 1.
- `collector_runs` records collector execution metadata and is the canonical
  place for run-level status/error summaries.
- This schema remains a CAL-70-preceding data-foundation boundary only. It
  supports collectors, storage, replay, and read-only inspection, not fair
  probability, strategy, edge, signal, paper trading, wallet, private key, or
  order workflows.

## 8. `collector_runs`

Run-level observability for source collectors.

| Field | Type | Nullable | Source | Notes |
|---|---:|---:|---|---|
| `run_id` | TEXT | no | Collector | Primary key. |
| `collector_name` | TEXT | no | Collector | Example: `polymarket_quote_recorder`. |
| `source` | TEXT | no | Collector | Example: `polymarket_clob_rest`, `cito_live`. |
| `source_status` | TEXT | no | Collector | Canonical status for the run. |
| `source_schema_version` | TEXT | yes | Collector | Parser/output contract version. |
| `started_at` | TEXT | no | System | Run start time. |
| `finished_at` | TEXT | yes | System | Run end time when completed. |
| `records_read` | INTEGER | no | Collector | Count before filtering. |
| `records_written` | INTEGER | no | Collector | Count written to storage. |
| `error_code` | TEXT | yes | Collector | Non-secret error class. |
| `error_message` | TEXT | yes | Collector | Sanitized message; no API key/token. |
| `raw_artifact_path` | TEXT | yes | Collector | Path to sanitized artifact if one exists. |

## Foreign Keys

```sql
resolved_markets.market_id -> markets.market_id
resolved_markets.match_id -> matches.match_id
resolved_markets.game_id -> games.game_id
games.match_id -> matches.match_id
game_state_snapshots.game_id -> games.game_id
draft_snapshots.match_id -> matches.match_id
draft_snapshots.game_id -> games.game_id
game_state_snapshots.collector_run_id -> collector_runs.run_id
```
