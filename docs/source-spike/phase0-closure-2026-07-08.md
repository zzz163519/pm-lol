# Phase 0 Closure Evidence Loop

> Local date: 2026-07-08 Asia/Shanghai
> Observed timestamps in raw JSON are UTC.
> Scope: read-only source / market / mapping validation only. No strategy, signal, model, wallet, private key, or order execution.

## Executive Conclusion

- Polymarket LOL Game Winner discovery and CLOB REST orderbook are rerunnable from this environment.
- LoLEsports livestats historical game sample still returns final picks, game state, gold, and objectives; game clock remains derived from frame timestamp only.
- One same-event Polymarket -> LoLEsports -> gameNumber -> team side mapping sample reached `mappingConfidence=1.0`.
- Phase 0 is still not a full pass because LoLEsports live latency and Polymarket Market WebSocket remain unvalidated.
- PandaScore and GRID are still commercial alternatives, not verified live backups in this run: PandaScore returned `403 Token is missing`; GRID docs confirm API key access is required.

## Raw Response Samples

New evidence from this run:

- `docs/source-spike/phase0-closure-polymarket-discovery-2026-07-08.json`
- `docs/source-spike/phase0-closure-blg-hle-mapping-2026-07-08.json`
- `docs/source-spike/pandascore-running-no-token-2026-07-08.http`
- `docs/source-spike/pandascore-docs-running-2026-07-08.md`
- `docs/source-spike/grid-docs-index-2026-07-08.md`

Updated / reused LoLEsports raw samples:

- `docs/source-spike/lolesports-115548128963037588-window-raw.json`
- `docs/source-spike/lolesports-115548128963037588-details-raw.json`
- `docs/source-spike/lolesports-115548128963037588-live-source-smoke.json`

## Commands And Results

### Polymarket discovery, orderbook, and same-event mapping

```bash
.venv/bin/python scripts/polymarket_discovery_smoke.py \
  --target-event-slug lol-blg-hle1-2026-07-09 \
  --lolesports-match-id 115570934355614575 \
  --max-events 8 \
  --retries 3 \
  --output docs/source-spike/phase0-closure-polymarket-discovery-2026-07-08.json \
  --mapping-output docs/source-spike/phase0-closure-blg-hle-mapping-2026-07-08.json
```

Result:

- `observedAt`: `2026-07-07T18:49:00.238353Z`
- API requests: `12`
- retries: `0`
- error classes: `[]`
- Polymarket LOL page: HTTP 200, `1460592` bytes
- Gamma slug detail for `lol-blg-hle1-2026-07-09`: HTTP 200, `214915` bytes
- LoLEsports `getEventDetails?id=115570934355614575`: HTTP 200
- LoLEsports `getSchedule`: HTTP 200
- CLOB `/book` for Game 1 BLG token: HTTP 200

Orderbook sample:

```text
marketSlug: lol-blg-hle1-2026-07-09-game1
conditionId: 0x86d9c29b6bd497d00ea0bfd1341caf040bbf7e04bc603a55f0353f2594f0f17c
tokenId: 34899681629975596680823272511407820643214154601485383259115476523364469117569
outcome: Bilibili Gaming
bidCount: 20
askCount: 22
bestBid: 0.41
bestAsk: 0.44
sourceTimestamp: 1783450142732
```

### LoLEsports livestats smoke

```bash
.venv/bin/python scripts/lolesports_live_source_smoke.py \
  --game-id 115548128963037588 \
  --output-dir docs/source-spike \
  --timeout-sec 20
```

Result:

- `overallOk`: `true`
- `gameId`: `115548128963037588`
- `window.statusCode`: `200`
- `details.statusCode`: `200`
- `window.sourceTimestamp`: `2026-06-14T06:27:24.531Z`
- `details.sourceTimestamp`: `2026-06-14T06:27:24.531Z`
- `window.sourceLatencySec`: `2031695.706`
- `details.sourceLatencySec`: `2031696.6`

The large latency values are expected because this is a historical game sample. They prove timestamp extraction and calculation, not live latency.

### PandaScore unauthenticated probe

```bash
curl -s -i https://api.pandascore.co/lol/matches/running
```

Result:

```text
HTTP/2 403
{"error":"Token is missing"}
```

Conclusion: no tokenless live validation path was available in this run. PandaScore remains a commercial backup candidate requiring an API key / plan before field and latency proof.

### GRID public documentation probe

```bash
curl -s https://r.jina.ai/https://docs.grid.gg/
```

Result summary:

- Documentation index was reachable.
- It describes static data and in-game live data feeds.
- It states an authorised API key is required through the `x-api-key` header for GraphQL API access.

Conclusion: GRID remains the likely highest-quality official upgrade path, but this run did not verify live fields or latency because access requires an API key.

## Field Checklist

### LoLEsports live-state fields

From `docs/source-spike/lolesports-115548128963037588-live-source-smoke.json`:

| Field | Status | Note |
|---|---|---|
| final picks | present | Derived from `gameMetadata.*TeamMetadata.participantMetadata[].championId`. |
| game clock | derived only | No explicit clock field; derivable from frame timestamps only. |
| game state | present | `sampleFrame.gameState`. |
| gold | present | blue/red `totalGold`. |
| objectives | present | towers, dragons, barons, inhibitors coverage present. |

Limitation:

- Live `sourceLatencySec` is still pending because no active live sample was captured in this run.

### Polymarket market/orderbook fields

From `docs/source-spike/phase0-closure-polymarket-discovery-2026-07-08.json`:

| Field | Status | Note |
|---|---|---|
| event slug | present | `lol-blg-hle1-2026-07-09`. |
| event title | present | BLG vs HLE BO5 MSI Playoffs. |
| event startTime | present | `2026-07-09T08:00:00Z`. |
| Game Winner markets | present | Game 1/2/3/4 Winner discovered. |
| conditionId | present | Per Game Winner market. |
| outcomes | present | BLG / HLE. |
| clobTokenIds | present | Two token IDs per market. |
| orderbook bids/asks | present | CLOB `/book` sample read successfully. |
| bestBid/bestAsk | present | Game 1 BLG token `0.41 / 0.44`. |

Limitations:

- Generic Gamma keyword search remains unreliable.
- No Game 5 Winner market was observed in current documented samples.
- Market WebSocket remains `pending_network_retest`.

## Mapping Sample

Source files:

- Full discovery: `docs/source-spike/phase0-closure-polymarket-discovery-2026-07-08.json`
- Mapping-only: `docs/source-spike/phase0-closure-blg-hle-mapping-2026-07-08.json`

Mapping conclusion:

```text
mappingConfidence: 1.0
viable: true
pendingLiveValidation: true
```

Basis:

- Polymarket event: `lol-blg-hle1-2026-07-09`
- Polymarket start time: `2026-07-09T08:00:00Z`
- LoLEsports matchId: `115570934355614575`
- LoLEsports start time: `2026-07-09T08:00:00Z`
- Team alignment: `Bilibili Gaming` -> `BILIBILI GAMING` / `BLG`; `Hanwha Life Esports` -> `Hanwha Life Esports` / `HLE`
- Game Winner markets: Game 1/2/3/4 all mapped to LoLEsports game IDs and sides.

Concrete Game 1 sample:

| Market token outcome | tokenId | LoLEsports gameId | gameNumber | teamId | teamCode | side | confidence |
|---|---|---|---:|---|---|---|---:|
| Bilibili Gaming | `34899681629975596680823272511407820643214154601485383259115476523364469117569` | `115570934355614576` | 1 | `99566404853854212` | BLG | red | 1.0 |
| Hanwha Life Esports | `92155896711226508531656306422645708487529460510087463062559535463800385306518` | `115570934355614576` | 1 | `100205573496804586` | HLE | blue | 1.0 |

This closes the static same-event mapping sample gate for one event. It does not close live latency.

## Latency And Limits

- LoLEsports historical `sourceLatencySec` is computable, but not a live latency proof.
- Polymarket CLOB book includes `sourceTimestamp`, but this smoke did not compute local latency for CLOB because the existing summary only records source timestamp and observed request diagnostics.
- PandaScore cannot be validated without a token; unauthenticated live endpoint returns 403.
- GRID cannot be validated without authorised API access; docs indicate API key is required.
- Current network path used proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy` true in diagnostics). No TLS failure occurred in this run.

## Suggested Doc Updates After Hermes Acceptance

### `roadmap.md`

- Change the Phase 1 remaining gate from "真实同场 mapping validation pending" to "one pre-match static same-event mapping sample passed; require repeated live/near-live samples before full Phase 0 pass".
- Keep LoLEsports live latency and Polymarket WebSocket as remaining Phase 0 gates.
- Keep Phase 2+ frozen.

### `tasks.md`

- Under `F0-05`, mark the same-event Polymarket mapping sample as completed for BLG vs HLE:
  `lol-blg-hle1-2026-07-09-game1 -> matchId 115570934355614575 -> gameId 115570934355614576 -> BLG red / HLE blue`, `mappingConfidence=1.0`.
- Under Phase 0 blockers, replace "Real cross-event mapping validation" with "repeat mapping validation across more events/leagues and live/near-live windows".
- Under `F0-06`, add the 2026-07-08 CLOB rerun result: Game 1 BLG token `bestBid=0.41`, `bestAsk=0.44`, `bidCount=20`, `askCount=22`.
- Under `F0-01`, record unauthenticated PandaScore probe result: `403 Token is missing`.
- Under `F0-02`, record GRID docs access requirement: authorised API key required.

### `docs/source-score.md`

- Keep LoLEsports latency score pending; historical smoke passed, live latency not measured.
- Consider slightly improving Polymarket reliability evidence for REST polling in current network path, but do not change WebSocket risk.
- Keep PandaScore / GRID scores as expected/commercial estimates until tokened field samples exist.

### `docs/decision-log.md`

- Add a 2026-07-08 decision update: same-event static mapping sample reached `mappingConfidence=1.0`, so the previous "real cross-event mapping unproven" risk is partially reduced.
- Keep final go/no-go as `CONDITIONAL_GO_FOR_PHASE_1_DATA_FOUNDATION_WITH_PHASE_0_GATES`.
- Remaining hard blockers: LoLEsports active live latency and Polymarket WebSocket or explicit REST-polling baseline decision.
