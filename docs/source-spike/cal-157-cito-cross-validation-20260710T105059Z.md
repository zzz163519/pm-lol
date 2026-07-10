# CAL-157 CITO + LoLEsports + Polymarket Cross-validation

Observed from `2026-07-10T10:50:59.151801Z` through approximately
`2026-07-10T10:52:01Z`. This is a `no-active-match/near-live` sample, not a live
sample.

The CITO credential came only from the process environment and was used in the
`x-api-key` header. No credential value, length, hash, header value, or raw
secret-bearing request was printed or persisted.

## Source observations

| Source | Read-only request | HTTP | Business/source status | Freshness |
|---|---|---:|---|---|
| CITO | `GET /api/v1/lol/live` | 200 | `no_match`, `count=0`, `liveOnly=true` | `lastCheckedAt=2026-07-10T10:51:01.995Z` |
| CITO | `GET /api/v1/lol/schedule/today` | 200 | `partial_data`, 5 matches; target G2–LYON completed 0–3 | `dataFreshness=fresh`, `lastCheckedAt=2026-07-10T10:51:03.337Z` |
| CITO | `GET /api/v1/lol/live/115570934355614596/visual-state` | 200 | `no_live_match`; no numeric live fields | observed `2026-07-10T10:51:46.685Z` |
| LoLEsports | `getEventDetails` match `115570934355614593` | 200 | match completed; Games 1–3 completed | observed `2026-07-10T10:51:49.627Z` |
| LoLEsports | livestats window game `115570934355614596` | 200 | final picks present | observed `2026-07-10T10:51:53.569Z` |
| Polymarket | event/Gamma + public CLOB REST | 200 | Game 1–4 market/token mapping readable | orderbook source timestamp `2026-07-10T10:51:16.983Z`, 37.534 s old at discovery observation |

CITO reported `partial_data` for the schedule and warned that current match
data was repaired from Riot LoL Esports event details. That is recorded as a
limitation rather than treated as independent live confirmation.

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| identity | `PASS` | All three sources agree on G2 Esports vs LYON and LoLEsports match `115570934355614593`. |
| game | `PENDING` | The match had ended. CITO returned `no_live_match`, so gold, objectives, kills, clock, and live game state could not be cross-validated. |
| team side | `PENDING` | LoLEsports currently reports Game 3 as G2 blue / LYON red, but earlier live samples flipped and CITO had no active visual state for comparison. |
| market token side | `PASS` | Polymarket Game 1–4 retained named-team token mappings at `mappingConfidence=1.0`; this is mapping evidence only. |

## Decision

CAL-112 remains `NO-GO`; Phase 2 remains locked. Authenticated CITO read access
is now proven, but the required same-window active-match CITO live fields and
authoritative team-side stability remain unproven.

Structured artifact:
`docs/source-spike/cal-157-cito-cross-validation-20260710T105059Z.json`.

Scope remained read-only Data Foundation validation. No external write API,
strategy, prediction, fair probability, edge/signal, paper/live trading,
wallet, broker, private key, or order behavior was used or added.
