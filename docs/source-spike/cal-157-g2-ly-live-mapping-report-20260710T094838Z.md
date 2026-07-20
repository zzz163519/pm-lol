# CAL-157 G2 vs LYON Live Mapping Evidence

Observed at `2026-07-10T09:48:38.926396Z` and
`2026-07-10T09:54:44.462731Z`, 365.536335 seconds apart. The scheduled start
was `2026-07-10T08:00:00Z`.

This is genuinely live evidence, not a pre-match static sample. LoLEsports
reported match `115570934355614593` as `inProgress` in both samples, with
Games 1-2 `completed`, Game 3 `inProgress`, and Games 4-5 `unstarted`.

## Mapping

- Match: G2 Esports vs LYON, MSI BO5.
- LoLEsports teams: G2 Esports `98767991926151025`; LYON
  `99566405941863385`.
- Polymarket event: `lol-g2-ly-2026-07-10`.
- Polymarket Game Winner markets: Game 1-4, each with stable condition and
  outcome token IDs across both samples.
- `mappingConfidence`: `1.0` in both samples.
- Network: 15 requests, 0 retries, no error classes in each sample.

The match ID, game IDs, team IDs, market slugs, condition IDs, and token IDs
were stable. The Game 3 team-side mapping was not stable:

| Sample | G2 Esports | LYON |
|---|---|---|
| `09:48:38Z` | red | blue |
| `09:54:44Z` | blue | red |

## Conclusion

`PENDING` for CAL-112 closure.

- PASS: a true in-progress sample was captured twice.
- PASS: match/game/team identity and Polymarket market/token mappings reached
  `mappingConfidence=1.0`.
- PENDING: Game 3 blue/red side flipped between samples, so the complete
  `market -> match -> game -> team side` hard gate is not stable yet.
- PENDING: LoLEsports source latency remains unmeasured because the event
  details response has no source timestamp.
- PENDING: multi-event/league stability and Polymarket WebSocket retest remain
  separate gates.

CAL-112 should remain NO-GO until the authoritative side source is identified
and repeated live samples keep team side stable. Phase 2 remains frozen.

## Command

```bash
ts=$(date -u +%Y%m%dT%H%M%SZ); python scripts/polymarket_discovery_smoke.py --target-event-slug lol-g2-ly-2026-07-10 --lolesports-match-id 115570934355614593 --max-events 20 --retries 3 --output docs/source-spike/cal-157-g2-ly-discovery-${ts}.json --mapping-output docs/source-spike/cal-157-g2-ly-mapping-${ts}.json
```

The command was run twice, 365.536335 seconds apart.

## Source Payloads

- `docs/source-spike/cal-157-g2-ly-discovery-20260710T094838Z.json`
- `docs/source-spike/cal-157-g2-ly-mapping-20260710T094838Z.json`
- `docs/source-spike/cal-157-g2-ly-discovery-20260710T095444Z.json`
- `docs/source-spike/cal-157-g2-ly-mapping-20260710T095444Z.json`
- `docs/source-spike/cal-157-g2-ly-live-mapping-evidence-20260710T094838Z.json`

Scope is limited to read-only source, market discovery, and mapping
verification. No strategy, signal, fair probability, wallet, private key,
broker, order, or live trading logic was used or changed.
