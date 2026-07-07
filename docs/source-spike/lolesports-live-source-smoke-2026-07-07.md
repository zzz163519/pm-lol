# LoLEsports Live Source Smoke

> Date: 2026-07-07
> Scope: read-only livestats smoke for one known LoLEsports game ID
> Game ID: `115548128963037588`

## Command

```bash
.venv/bin/python scripts/lolesports_live_source_smoke.py --game-id 115548128963037588 --output-dir docs/source-spike --timeout-sec 20
```

## Raw Samples

- `docs/source-spike/lolesports-115548128963037588-window-raw.json`
- `docs/source-spike/lolesports-115548128963037588-details-raw.json`
- `docs/source-spike/lolesports-115548128963037588-live-source-smoke.json`

## Observed Result

- `overallOk`: `true`
- `window.statusCode`: `200`
- `details.statusCode`: `200`
- `window.sourceTimestamp`: `2026-06-14T06:27:24.531Z`
- `details.sourceTimestamp`: `2026-06-14T06:27:24.531Z`
- `window.sourceLatencySec`: `2030735.427`
- `details.sourceLatencySec`: `2030734.226`

## Field Coverage

- final picks: present
- game clock: derived from frame timestamps only
- gold: present
- objectives: present
- game state: present

## Limitations

- This run used a historical game ID, not an actively live match. The large
  `sourceLatencySec` values prove timestamp extraction/calculation works, but
  they do not validate live production latency.
- LoLEsports still does not expose an explicit `gameClock` field in this
  response shape; game clock remains derived from frame timestamps.
- This smoke only validates read-only source availability and sample capture. It
  does not permit strategy, signal, wallet, private key, or order execution
  work.

## Conclusion

The smoke is rerunnable and saves raw JSON plus a structured report. LoLEsports
livestats still returns window/details bodies for the tested game ID and covers
the Phase 0 candidate fields: final picks, game state, gold, and objectives.

Live latency remains pending until the same smoke is run against an active game.
