# LYON vs TSW Live Metrics / Latency Probe

Date: 2026-07-08 UTC

## Scope

Read-only CAL-54 live-game follow-up for Cito, LoLEsports livestats, and
Polymarket CLOB. No wallet, private key, order placement, strategy, prediction
model, or trading signal path was used.

Raw sample:

- `docs/source-spike/live-metrics-latency-probe-20260708T032203Z.json`

## Cito

Cito `visual-state` became useful during the sampled window. It returned
provisional but internally confident scoreboard frames:

| Observed at | Game clock | LYON kills | TSW kills | LYON gold | TSW gold | Gold diff | Sample age |
|---|---:|---:|---:|---:|---:|---:|---:|
| 03:22:06Z | 6:37 | 1 | 1 | 11400 | 10700 | +700 LYON | 22s |
| 03:22:26Z | 6:37 | 1 | 1 | 11400 | 10700 | +700 LYON | 43s |
| 03:22:59Z | 7:22 | 1 | 1 | 12800 | 12200 | +600 LYON | 32s |
| 03:23:28Z | 8:12 | 1 | 1 | 14200 | 13500 | +700 LYON | 13s |
| 03:24:02Z | 8:12 | 1 | 1 | 14200 | 13500 | +700 LYON | 41s |

Coverage caveat: Cito `/matches/{matchId}/coverage` still reported
`numeric_live_state=false` even while `visual-state` returned kills/gold/timer.
Treat `visual-state.status=provisional` plus `sampleAgeSeconds` as the practical
quality gate for now.

Cito `live/{gameId}/stats` was less useful for strategy metrics in this window:
it sometimes returned the 10 champion/player rows, but team totals and per-role
gold remained 0, with no source timestamp.

## LoLEsports

LoLEsports `livestats/window` and `details` were reachable, but the default
window stayed on an old source frame:

```text
latest observed source timestamp: 2026-07-08T03:14:28.962Z
observed request window: 2026-07-08T03:22:09Z to 2026-07-08T03:24:05Z
computed sourceLatencySec: ~459s to ~575s
```

It still exposed champion rows, but the available kills/gold/participant stats
were 0 and not usable for current live strategy metrics. Attempts to request
`startingTime` with recent ISO timestamps returned HTTP 400 or transient SSL
errors, so the default feed path did not provide a fresh live frame in this run.

## Polymarket CLOB

Polymarket Game 1 Winner market for `lol-ly-tsw-2026-07-08-game1` was readable.
Across 5 iterations and both outcomes:

```text
timestamp latency count: 10
min: -0.431s
median: 0.865s
mean: 0.795s
max: 2.461s
```

Observed top of book:

| Iteration | LYON bid/ask | TSW bid/ask | Orderbook timestamp latency |
|---:|---|---|---|
| 1 | 0.59 / 0.60 | 0.40 / 0.41 | -0.43s to -0.38s |
| 2 | 0.59 / 0.60 | 0.40 / 0.41 | 0.81s to 1.24s |
| 3 | 0.56 / 0.57 | 0.43 / 0.44 | 0.17s to 0.19s |
| 4 | 0.57 / 0.58 | 0.42 / 0.43 | 2.04s to 2.46s |
| 5 | 0.56 / 0.57 | 0.43 / 0.44 | 0.92s to 0.93s |

Small negative values are likely local clock / CLOB timestamp skew, not true
future data.

## Strategy-Relevant Verdict

```text
best_current_live_metrics_source = Cito visual-state
cito_visual_state_latency = sampleAgeSeconds 13-43s in this run
cito_kills_gold_objectives = present, provisional
cito_role_gold_diff = not available
lolesports_current_metrics = stale in this run
lolesports_champion_rows = present, but live frame stale
polymarket_clob_latency = ~0.9s median timestamp latency
polymarket_prices = readable
```

For this window, Cito visual-state is the only source that produced current-ish
kills, game clock, gold, and objectives. Neither Cito stats nor LoLEsports
livestats provided usable per-role / lane gold differences in the sampled
window.
