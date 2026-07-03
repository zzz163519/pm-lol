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

Current recommended discovery chain after the 2026-07-03 retest:

```text
Polymarket LOL page HTML -> event slug -> Gamma /events/slug/{slug} -> Game [1-5] Winner filter -> CLOB /book
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

## 2026-07-03 Retest: SSL / Discovery / Current Markets

Scope: read-only Polymarket page, Gamma slug detail, and CLOB `/book` checks. No wallet, no API key, no orders.

### Network Path

Observed proxy environment:

```text
HTTP_PROXY=http://192.168.240.1:7897
HTTPS_PROXY=http://192.168.240.1:7897
```

Observed behavior:

- Polymarket LOL page `HEAD` and `GET` succeeded through the proxy at times with `HTTP/2 200`.
- The same page and Gamma endpoints intermittently failed with `OpenSSL SSL_connect: SSL_ERROR_SYSCALL`.
- Clearing proxy variables and using direct/no-proxy mode failed for the Polymarket page with `SSL_ERROR_SYSCALL`.
- Forcing `curl --http1.1` is not a reliable universal workaround: a previous attempt succeeded, but the 2026-07-03 retest also observed `--http1.1` failing after proxy CONNECT.
- Polymarket returned Cloudflare/Vercel headers on successful page requests, so the service and page were reachable from this environment.

Interpretation:

```text
ssl_failure_cause = current WSL/proxy/direct-network TLS negotiation instability
polymarket_service_status = reachable
http1_1_workaround = not_reliable_as_sole_fix
required_collector_behavior = retry_backoff_and_error_classification
```

### Page HTML Slug Discovery

The page HTML was fetched to `/tmp/pm_lol_polymarket_lol.html` during the retest.
The HTML directly exposed these LOL event slugs:

- `lol-ly-fur-2026-07-03`
- `lol-blg-t1-2026-07-04`
- `lol-tsw-tes-2026-07-04`
- `lol-hle1-g2-2026-07-05`

The page text did not reliably expose concrete `Game 1 Winner` / `Game 2 Winner`
strings, so page scraping alone is not enough. It should be used to discover
event slugs, then Gamma slug detail should be used for market metadata.

### Gamma Generic Search

Generic Gamma search remains unreliable for LoL discovery:

```text
GET /events?limit=5&active=true&closed=false&search=league%20of%20legends
GET /events?limit=5&active=true&closed=false&search=lol
GET /events?limit=5&active=true&closed=false&search=t1
```

These returned `HTTP 200` in some attempts but surfaced unrelated results such as:

- `kraken-ipo-in-2025`
- `macron-out-in-2025`
- `uk-election-called-by`

The `msi` search also hit repeated TLS failures in this environment. Do not use
generic keyword search as the primary discovery path.

### Gamma Slug Detail

Direct Gamma event lookup by slug was viable and returned Game Winner markets.

Validated current event examples:

| Event slug | Event title | Event startTime | Result |
|---|---|---|---|
| `lol-ly-fur-2026-07-03` | LoL: LYON vs FURIA Esports (BO5) - Mid-Season Invitational Playoffs | `2026-07-04T03:00:00Z` | BO5 series + Game 1/2/3/4 Winner |
| `lol-blg-t1-2026-07-04` | LoL: Bilibili Gaming vs T1 (BO5) - Mid-Season Invitational Playoffs | `2026-07-04T08:00:00Z` | BO5 series + Game 1/2/3/4 Winner |
| `lol-tsw-tes-2026-07-04` | LoL: Team Secret Whales vs Top Esports (BO5) - Mid-Season Invitational Playoffs | `2026-07-05T03:00:00Z` | BO5 series + Game 1/2/3/4 Winner |
| `lol-hle1-g2-2026-07-05` | LoL: Hanwha Life Esports vs G2 Esports (BO5) - Mid-Season Invitational Playoffs | `2026-07-05T08:00:00Z` | Game 1/2/3/4 Winner |

No `Game 5 Winner` market was observed in these current samples. Some Game 5
props existed, such as dragon, inhibitor, and kill props, but those are outside
the current Phase 1 `Game N Winner` scope.

### Selected Current Market / CLOB Check

Selected current market:

```text
eventSlug: lol-blg-t1-2026-07-04
marketSlug: lol-blg-t1-2026-07-04-game1
question: LoL: Bilibili Gaming vs T1 - Game 1 Winner
conditionId: 0x52671a734b1872bab38ddaf5113a4716fb81b5bfb9e794475fadbea0fbacf0cf
outcomes: Bilibili Gaming / T1
clobTokenIds:
  Bilibili Gaming: 54346906519017004815826838861276314699310042763673409676887565361940723790357
  T1: 80610833884813301020603329107861729554436766570394247888281033135395406870833
```

CLOB `/book` result for the Bilibili Gaming token:

```text
bids = 30
asks = 31
bestBid = 0.47
bestAsk = 0.48
```

This confirms that an active/current `Game N Winner` token can be discovered
through slug detail and quoted through the public CLOB book endpoint.

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
