# Polymarket Public Market Data Spike

> Date: 2026-06-15
> Task: F0-06
> Scope: read-only Gamma API and CLOB public endpoint validation. No wallet, no API key, no orders.

## Summary

Polymarket public REST endpoints are sufficient for Phase 1's first `QuoteRecorder` version based on polling.

Validated chain:

```text
eventSlug -> Gamma event -> Game Winner market -> conditionId -> clobTokenIds -> CLOB orderbook -> bestBid/bestAsk
```

Market WebSocket was not validated in this network environment because the WebSocket host timed out during the opening handshake. This should be retested from a clean network path before relying on push updates.

## Search Path

Successful direct event lookup:

```text
GET https://gamma-api.polymarket.com/events/slug/lol-ktc-sgw-2026-06-15
```

The response contained 23 markets, including:

- Game 1 Winner
- Game 2 Winner
- Match Winner
- O/U 2.5 Games
- Game Handicap
- several low-liquidity game props

Keyword search was also tested:

```text
GET https://gamma-api.polymarket.com/events?limit=5&active=true&closed=false&search=league%20of%20legends
```

This returned unrelated results first, so Phase 1 should not rely on generic text search alone. A better resolver should combine category/slug discovery, event pages, and title filters.

## Selected Market

Saved sample:

```text
docs/source-spike/polymarket-market-sample.json
```

Selected market:

```text
eventSlug: lol-ktc-sgw-2026-06-15
marketSlug: lol-ktc-sgw-2026-06-15-game2
question: LoL: KT Rolster Challengers vs Saigon Warriors - Game 2 Winner
conditionId: 0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553
outcomes: KT Rolster Challengers / Saigon Warriors
clobTokenIds:
  KT Rolster Challengers: 100172814846746500028191734405612966589475835807067790171955690167538278072521
  Saigon Warriors: 45237782937761666957430863754762402074289825813292595850496859818516586364597
```

## CLOB Orderbook

Tested endpoints:

```text
GET  https://clob.polymarket.com/book?token_id={tokenId}
POST https://clob.polymarket.com/books
GET  https://clob.polymarket.com/price?token_id={tokenId}&side=BUY
GET  https://clob.polymarket.com/price?token_id={tokenId}&side=SELL
```

Saved sample:

```text
docs/source-spike/polymarket-orderbook-sample.json
```

Game 2 Winner orderbook summary:

| Outcome | tokenId suffix | bestBid | bestAsk | spread | bidLevels | askLevels |
|---|---:|---:|---:|---:|---:|---:|
| KT Rolster Challengers | 072521 | 0.791 | 0.801 | 0.010 | 36 | 17 |
| Saigon Warriors | 364597 | 0.199 | 0.209 | 0.010 | 17 | 36 |

Depth near top of book:

```text
KT token: bidDepthWithin1c=635.52, askDepthWithin1c=213.77
SGW token: bidDepthWithin1c=213.77, askDepthWithin1c=635.52
```

Game 1 Winner was also readable, but it was effectively one-sided when tested:

```text
KT token: bestBid=0.999, bestAsk=null
SGW token: bestBid=null, bestAsk=0.001
```

This confirms the system must record empty-side books and not assume both sides are always tradable.

## WebSocket Test

Target:

```text
wss://ws-subscriptions-clob.polymarket.com/ws/market
```

Subscription payload:

```json
{
  "assets_ids": [
    "100172814846746500028191734405612966589475835807067790171955690167538278072521",
    "45237782937761666957430863754762402074289825813292595850496859818516586364597"
  ],
  "type": "market"
}
```

Saved sample:

```text
docs/source-spike/polymarket-ws-sample.json
```

Result:

```text
status = handshake_timeout_in_current_network
messageCount = 0
```

Attempts with Python `websockets`, direct/no-proxy mode, `npx wscat`, and a curl HTTP upgrade probe all failed before receiving a WebSocket response. REST calls to Gamma and CLOB succeeded from the same environment.

Interpretation: WebSocket support is not disproven, but it is not validated from this machine/network. Phase 1 can start with REST polling and keep WebSocket as a follow-up validation task.

## Errors / Limits Observed

- No 403 or 429 from Gamma event lookup.
- No 403 or 429 from CLOB `/book`, `/books`, or `/price`.
- `curl --noproxy '*'` hung for Polymarket domains in this environment; normal proxy-backed curl worked.
- WebSocket TLS/opening handshake timed out.

## Phase 1 Judgment

```text
public_market_discovery = usable
public_orderbook_polling = usable
public_market_websocket = pending_network_retest
quote_recorder_v1 = feasible_with_rest_polling
```

Conclusion: Phase 1 can build a public endpoint based `QuoteRecorder` without wallet/API key by polling Gamma for market metadata and CLOB REST for orderbooks. WebSocket should be retried from a clean network path before it is required for production.
