# Cito-first Live Retest

Date: 2026-07-08 UTC

Scope: read-only CAL-54 retest using Cito as the first in-game source for LYON vs TSW. No wallet, private key, order placement, strategy model, prediction, or trading signal path was used.

Raw sample: `cito-primary-live-retest-20260708T033938Z.json`

## Cito GET Usage Confirmed

- Base URL: `https://api.citoapi.com/api/v1`
- Auth header: `x-api-key: YOUR_CITO_API_KEY`
- Public docs page confirms the League of Legends GET examples.
- Dashboard endpoints page was not publicly readable through the web reader; it resolved to the Cito sign-in page, so the detailed dashboard UI requires an authenticated Cito session.
- Endpoint manifest confirms the live/in-game REST paths used below, including `/lol/live`, `/lol/matches/{matchId}/coverage`, `/lol/live/{matchId}/series`, `/lol/live/{gameId}/visual-state`, `/lol/live/{gameId}/stats`, `/lol/live/{gameId}/window`, `/lol/live/{gameId}/details`, `/lol/live/{gameId}/events`, and game-level stats/gold/objective endpoints.

## Current Cito-first Result

Latest visual-state samples:

| Observed at | Status | Game clock | LYON kills | TSW kills | LYON gold | TSW gold | Gold diff | Towers | Dragons | Barons | Sample age |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|
| 03:38:28Z | replay | 22:18 | 7 | 8 | 42400 | 40900 | +1500 LYON | 4-2 | 3-0 | 0-0 | 8s |
| 03:38:56Z | replay | 22:18 | 7 | 8 | 42400 | 40900 | +1500 LYON | 4-2 | 3-0 | 0-0 | 34s |
| 03:39:21Z | stale | 22:18 | 7 | 8 | 42400 | 40900 | +1500 LYON | 4-2 | 3-0 | 0-0 | 114s |

Interpretation:

- `matchId`: `115570934355614587`
- `gameId`: `115570934355614588`
- Cito `visual-state` still carries accepted top-level `blueTeam` / `redTeam`
  totals and `lastKnownGameplayState`.
- It is not fresh enough to treat as current live state in the latest sample:
  `freshness.isFresh=false`, stale threshold is 45s, latest `sampleAgeSeconds`
  is 114s.
- The same values are mirrored in `GET /lol/games/{gameId}/gold` and
  `postgame.goldGraph`, both currently partial.

## Player / Lane Rows

Best available row source in this retest is Cito live/game stats. Presence of rows does not automatically mean lane gold is usable; zero or missing gold values remain unusable for matchup gold-diff.

| Team | Role | Player | Champion | K/D/A | Gold | CS |
|---|---|---|---|---:|---:|---:|
| blue | top | LYON Dhokla | Renekton | 0 / 0 / 0 | 0 | 0 |
| blue | jungle | LYON Inspired | Trundle | 0 / 0 / 0 | 0 | 0 |
| blue | mid | LYON Saint | Taliyah | 0 / 0 / 0 | 0 | 0 |
| blue | bottom | LYON Berserker | Ezreal | 0 / 0 / 0 | 0 | 0 |
| blue | support | LYON Isles | Alistar | 0 / 0 / 0 | 0 | 0 |
| red | top | TSW Pun | Volibear | 0 / 0 / 0 | 0 | 0 |
| red | jungle | TSW Hizto | Lee Sin | 0 / 0 / 0 | 0 | 0 |
| red | mid | TSW Dire | Sylas | 0 / 0 / 0 | 0 | 0 |
| red | bottom | TSW Eddie | Kai'Sa | 0 / 0 / 0 | 0 | 0 |
| red | support | TSW Bie | Nautilus | 0 / 0 / 0 | 0 | 0 |

## Endpoint Health Latest Iteration

| Endpoint label | HTTP | Payload status | Data type | Data len | Bytes | Req sec |
|---|---:|---|---|---:|---:|---:|
| live | 200 | live | list | 1 | 2637 | 0.496 |
| matches_live | 200 | live | list | 1 | 2645 | 0.409 |
| match_coverage | 200 | None | dict |  | 2186 | 0.632 |
| live_series | 200 | None | dict |  | 3867 | 0.69 |
| live_visual_state | 200 | stale | NoneType |  | 1807 | 0.664 |
| live_stats | 200 | None | dict |  | 5522 | 0.46 |
| live_window | 200 | None | dict |  | 1507 | 0.416 |
| live_details | 200 | None | dict |  | 3466 | 0.527 |
| live_events | 200 | no_results | list | 0 | 915 | 0.442 |
| match_games | 200 | None | list | 1 | 876 | 0.513 |
| match_stats | 200 | None | dict |  | 345 | 0.516 |
| match_player_stats | 200 | None | list | 1 | 1357 | 0.64 |
| match_timeline | 200 | no_results | list | 0 | 948 | 0.535 |
| game_detail | 200 | None | dict |  | 874 | 0.513 |
| game_stats | 200 | no_results | list | 0 | 1237 | 0.495 |
| game_player_stats | 200 | no_results | list | 0 | 1244 | 0.517 |
| game_timeline | 200 | no_results | list | 0 | 937 | 0.55 |
| game_gold | 200 | None | list | 18 | 1252 | 0.526 |
| game_objectives | 200 | no_results | list | 0 | 939 | 0.532 |
| game_postgame | 200 | None | dict |  | 1897 | 0.6 |
| game_plates | 200 | None | NoneType |  | 433 | 0.634 |
| game_distributions | 200 | None | dict |  | 463 | 0.633 |
| game_vision | 200 | None | NoneType |  | 433 | 0.586 |
| game_jungle_share | 200 | None | NoneType |  | 439 | 0.723 |
| analytics_drafts | 200 | None | dict |  | 513 | 0.719 |

## Polymarket Latency Context

Game 1 CLOB orderbook was read only as market-latency context for the same event slug `lol-ly-tsw-2026-07-08`.

Latency summary: count=6, min=-0.045, median=0.096, mean=0.191, max=0.685 seconds.

| Iteration | Outcome | Best bid | Best ask | Timestamp latency sec |
|---:|---|---:|---:|---:|
| 1 | LYON | 0.68 | 0.69 | 0.28 |
| 1 | Team Secret Whales | 0.31 | 0.32 | 0.685 |
| 2 | LYON | 0.68 | 0.69 | 0.036 |
| 2 | Team Secret Whales | 0.31 | 0.32 | 0.112 |
| 3 | LYON | 0.68 | 0.69 | -0.045 |
| 3 | Team Secret Whales | 0.31 | 0.32 | 0.08 |

## Verdict

Cito should be the first in-game source for this match when `visual-state`
returns fresh accepted gameplay state: it is the documented Cito near-live
endpoint for game time, kills, gold, towers, dragons, and barons.

This retest shows the exact gating needed:

- Acceptable live scoreboard surface: `live/{gameId}/visual-state` only when the
  top-level or `data`/`lastKnownGameplayState` values are accepted and
  `sampleAgeSeconds <= 45`.
- Current latest state: usable as last-known evidence, not fresh live input.
- Gold graph: `games/{gameId}/gold` is available and aligns with visual-state
  last-known total gold.
- Per-role / matchup gold diff: still not available. `live/stats`,
  `live/window`, and `live/details` contain champion/player rows, but all kills,
  CS, and player gold are still zero.
- Objectives: visual-state top-level team totals are usable in last-known form;
  `games/{gameId}/objectives` still returns `no_results`.

If `visual-state` returns `not_ready`, `on_break`, empty data, or high `sampleAgeSeconds`, the source should be treated as not currently usable rather than falling through silently. Dashboard endpoint details could not be verified from the public page because it requires sign-in.
