# CAL-169 HLE vs LYON Active Three-source Mapping Evidence

Observed at `2026-07-11T08:02:37.499Z` and `2026-07-11T08:08:26.091Z`,
348.592 seconds apart. Both are genuinely active samples: LoLEsports match
`115570934355614599` reported Game 1 `115570934355614600` as `inProgress`.

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| identity | `PASS` | HLE `100205573496804586`, LYON `99566405941863385`, match and game IDs were stable. |
| game | `PENDING` | CITO coverage and visual-state returned HTTP 200, but visual state changed from `on_break` to `not_ready` and exposed no numeric gameplay fields. |
| team side | `PENDING` | Game 1 changed from HLE blue / LYON red to HLE red / LYON blue between samples. |
| market token side | `PASS` | Polymarket `lol-hle1-ly-2026-07-11` Game 1-4 condition/token IDs and named outcomes were stable; `mappingConfidence=1.0` twice. |
| freshness / latency | `PENDING` | CITO reported `sampleAgeSeconds=1` in the first sample but no accepted frame; LoLEsports event details has no source timestamp, and livestats returned one TLS failure then HTTP 204. |

The active capture requirement passes, but the complete three-source
`market -> match -> game -> team side` hard gate remains pending. This new
event reproduces the side flip seen in CAL-157, and CITO did not provide an
independent numeric or team-side frame. CAL-112 remains NO-GO and Phase 2
remains frozen.

## Artifacts

- `docs/source-spike/field-source-map-probe-20260711T080237499Z.json`
- `docs/source-spike/field-source-map-probe-20260711T080826091Z.json`
- `docs/source-spike/cal-169-hle-ly-discovery-20260711T080237Z.json`
- `docs/source-spike/cal-169-hle-ly-mapping-20260711T080237Z.json`
- `docs/source-spike/cal-169-hle-ly-discovery-20260711T080826Z.json`
- `docs/source-spike/cal-169-hle-ly-mapping-20260711T080826Z.json`

The CITO credential was loaded only from the controlled server environment
and sent through `x-api-key`; it was not printed or persisted. All operations
were read-only. No strategy, prediction, fair probability, signal, wallet,
private key, broker, order, or trading behavior was used or added.
