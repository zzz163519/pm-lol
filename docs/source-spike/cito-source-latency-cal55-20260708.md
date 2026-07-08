# CAL-55 Cito Source Latency Probe

Window: `2026-07-08T04:13:54.491Z` to `2026-07-08T04:19:22.082Z` UTC.

Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.

## Inputs

- Cito endpoint: `/api/v1/lol/live/115570934355614589/visual-state`
- Polymarket market: `lol-ly-tsw-2026-07-08-game2`
- Samples: `29` at requested interval `10s`

## Latency

- Cito sourceLatencySec: `proxy_only_sampleAgeSeconds_not_true_observedAt_minus_source_timestamp`.
- Cito proxy range from `sampleAgeSeconds`: min `1`, median `24`, mean `23.241`, max `49` seconds.
- Polymarket CLOB timestamp latency: min `-0.606`, median `0.069`, mean `0.283`, max `1.965` seconds.

Cito did not expose a usable server source timestamp in this response shape; `sampleAgeSeconds` is therefore a freshness proxy, not true `observedAt - sourceTimestamp` latency.

## Confidence

- Observed unique confidence maps: `[{"broadcastState": 1, "gold": 1, "kills": 1, "objectives": 1, "seriesScore": 0, "teams": 1, "timer": 1}, {"broadcastState": 1, "gold": 1, "kills": 1, "objectives": 1, "seriesScore": 1, "teams": 1, "timer": 1}]`
- Tracked requested fields (`gold/kills/objectives/timer`) all stayed at `1`: `True`
- Conclusion: `tracked_fields_always_one_treat_as_unverified_not_calibrated`.

## Verdict

Cito visual-state is acceptable only as a candidate backup/live input behind a freshness gate in the observed proxy range, not as a confirmed primary source: this run measured `sampleAgeSeconds` 1-49s and still lacks a true source timestamp. Treat confidence=1 fields as uncalibrated until Cito documents their semantics or a postgame reconciliation proves accuracy.

Raw JSON: `docs/source-spike/cito-source-latency-cal55-20260708.json`
