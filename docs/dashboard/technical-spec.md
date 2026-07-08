# PM-LOL Dashboard Technical Spec

Status: Phase 1 read-only monitoring design. This document is a technical plan
only. It does not implement dashboard code, strategy logic, prediction models,
trading signals, wallet integration, private key handling, or order placement.

The implementation card should start only after CAL-53 finishes the live loop
verification handoff. Until then this spec is a target shape for a local
browser dashboard inside the existing `pm-lol` repository.

## 1. Technical Stack

### Recommendation

Use a TypeScript dashboard app under the existing repository, with the Python
data foundation kept as the ingestion/storage layer:

- Backend API server: Fastify + TypeScript.
- Frontend: Vite + React + TypeScript.
- Storage: SQLite cache/read model, reusing the Phase 1 schema direction from
  `docs/schema-phase1.md`.
- Local deployment: one local command, `npm run dev:dashboard`, reachable from
  WSL and the host browser.

### Why Fastify

Fastify is a better Phase 1 fit than a heavier framework because the dashboard
needs a small HTTP/SSE surface, predictable JSON schemas, and low local setup
cost. It gives enough structure for route plugins and typed request/response
contracts without forcing a larger application framework.

Express would be acceptable but provides less built-in schema discipline. Hono
would also work, but Fastify is more conventional for a local Node API server
with WebSocket/SSE and SQLite access. The current repository is Python-only, so
TypeScript should be isolated under `dashboard/` rather than mixed into
`src/pm_lol/`.

### Why React

The interface is stateful: current match list, selected match/game, live
snapshots, quote freshness, historical snapshot filters, and later Phase 2/4
display slots. React keeps this manageable without building a custom client
state layer. Vite provides the simplest local developer loop.

htmx is viable for a simpler server-rendered page, but it becomes awkward once
the page needs live updates, chart refresh, side-by-side market/source state, and
later probability/order-adapter status panels. React is the more durable choice
for this dashboard.

### SQLite Role

SQLite is required for Phase 1, not optional, because the dashboard must show
both live state and historical snapshots. It should be treated as a local cache
and evidence store, not as a trading system database.

The dashboard API reads from SQLite for:

- current matches and games;
- latest visual-state snapshots;
- latest Polymarket quotes;
- resolved market mappings;
- historical snapshot queries.

The adapters may write raw source payloads and normalized snapshot rows through
the storage layer. API routes should not call Cito or Polymarket directly except
through adapters.

### Repository Layout

Suggested implementation layout:

```text
dashboard/
  package.json
  vite.config.ts
  server/
    index.ts
    routes/
    adapters/
    storage/
    view-models/
  client/
    src/
      App.tsx
      api/
      components/
      views/
docs/dashboard/technical-spec.md
```

The existing Python code remains the source spike and conditional data
foundation. Phase 1 can either keep Python ingestion scripts writing SQLite and
let the dashboard server read those rows, or port the read-only pollers into the
TypeScript adapter layer. The first implementation should prefer the least
duplicative path: reuse existing Python collectors where they already exist, and
add TypeScript adapters only for the dashboard live loop surface that needs
server-side subscription semantics.

## 2. Data Flow Design

### Cito Visual-State Flow

Cito is the Phase 1 primary source for team identity, gold, goldDiff,
objectives, kills, gameClock, and gameState per the 2026-07-08 decision log.
LoLEsports remains the draft/picks supplement.

Flow:

```text
Cito schedule/today
  -> CitoAdapter discovers current matches
  -> resolver maps match/game/team IDs to local MatchView IDs
  -> Cito visual-state poll loop per subscribed match/game
  -> normalize to GameStateUpdate
  -> write raw payload + normalized snapshot to SQLite
  -> publish update on in-process event bus
  -> Fastify SSE stream
  -> React match detail view
```

Polling cadence should default to 15-30 seconds and be configurable. The
dashboard should show `observedAt`, source timestamp if available, and stale
status. Because the project is not pursuing second-level latency, stale warnings
should be informational for monitoring, not trading gates.

If Cito returns an empty live set, missing visual-state, a 401/403, a 429, or a
schema mismatch, the adapter must emit a source status update with the failure
reason. It must not fabricate fallback live state.

### LoLEsports Draft/Picks Flow

LoLEsports is used for final picks and patch data when Cito visual-state does
not provide reliable draft coverage.

```text
LoLEsports event details / livestats
  -> LoLEsportsDraftAdapter polls or loads known game IDs
  -> normalize final picks to DraftUpdate
  -> write draft snapshots to SQLite
  -> merge into MatchDetailView by matchId/gameId/team side
```

The dashboard should display draft state as `pending`, `partial`, `final`, or
`unavailable`. Draft absence must be visible as source status, not hidden behind
empty champion slots.

### Polymarket CLOB Price Flow

Polymarket remains the market/orderbook source. Phase 1 should use REST polling
as the baseline unless the Market WebSocket retest is later accepted.

```text
Polymarket LOL page / known event slug
  -> Gamma event slug detail
  -> Game N Winner market filter
  -> market-match resolver hard gate
  -> token IDs for mapped outcomes
  -> PolymarketAdapter polls CLOB /book per token
  -> normalize to PriceUpdate
  -> write quote snapshots to SQLite
  -> publish update on in-process event bus
  -> React market panel
```

The quote panel should show yes/no or outcome-token prices using the mapped
team names, with bid, ask, mid, spread, bid depth, ask depth, volume, and quote
freshness where available. If mapping confidence is below the project threshold,
the market must appear as skipped/low-confidence and should not be joined to a
live game view.

### Dual-Source Merged View

The dashboard server should assemble a read model rather than making the React
client join raw source records.

```text
matches + games
  + latest Cito visual-state by gameId
  + latest LoLEsports draft by gameId/team side
  + resolved_markets where mapping_confidence >= 0.90
  + latest Polymarket quotes by conditionId/tokenId
  -> MatchDetailView
```

The merge key is the resolver output:

- `matchId`
- `gameId`
- `gameNumber`
- `blueTeamId`
- `redTeamId`
- Polymarket `conditionId`
- Polymarket outcome token IDs

The front end receives one `MatchDetailView` containing source freshness and
source status per panel. This keeps mapping and source-failure rules in one
backend seam.

## 3. Data Source Adapter Interface

### Module / Interface / Seam

The module is the dashboard data-source layer. Its public interface is
`DataSourceAdapter<TUpdate>`. The seam is the boundary between remote-owned
source APIs and the local dashboard read model. Adapter implementations hide
authentication, polling, retry classification, source-specific payloads, and
normalization. Callers only know how to connect, subscribe to match/game scope,
receive updates, and disconnect.

This interface is deeper than a pass-through API wrapper because one small
surface unlocks polling, source status, raw evidence capture, normalized updates,
and future adapter replacement without changing the React UI.

Dependencies:

- Cito API: true external.
- Polymarket Gamma/CLOB: true external.
- LoLEsports frontend API: true external.
- SQLite: local-substitutable.
- React client: in-process HTTP/SSE consumer from the API server perspective.

### Type Contract

```ts
export type DataSourceKind =
  | "cito_visual_state"
  | "lolesports_draft"
  | "polymarket_clob"
  | "polymarket_order"
  | "fair_probability"
  | "grid"
  | "pandascore";

export type SourceStatus =
  | "idle"
  | "connecting"
  | "ready"
  | "polling"
  | "stale"
  | "rate_limited"
  | "auth_failed"
  | "schema_mismatch"
  | "unavailable"
  | "error"
  | "disconnected";

export interface SubscriptionScope {
  matchId: string;
  gameId?: string;
  gameNumber?: number;
  conditionId?: string;
  tokenIds?: string[];
}

export interface SourceStatusUpdate {
  adapter: DataSourceKind;
  status: SourceStatus;
  observedAt: string;
  message?: string;
  retryAfterSec?: number;
  rawEvidencePath?: string;
}

export interface BaseUpdate {
  adapter: DataSourceKind;
  matchId: string;
  gameId?: string;
  observedAt: string;
  sourceTimestamp?: string;
  rawEvidencePath?: string;
  confidence: number;
}

export interface GameStateUpdate extends BaseUpdate {
  adapter: "cito_visual_state" | "grid" | "pandascore";
  gameClockSec?: number;
  gameState: "not_started" | "draft" | "in_game" | "paused" | "finished" | "unknown";
  blueTeamId: string;
  redTeamId: string;
  blueGold?: number;
  redGold?: number;
  goldDiff?: number;
  blueKills?: number;
  redKills?: number;
  objectives: {
    blueTowers?: number;
    redTowers?: number;
    blueDragons?: string[];
    redDragons?: string[];
    blueBarons?: number;
    redBarons?: number;
    blueInhibitors?: number;
    redInhibitors?: number;
  };
}

export interface DraftUpdate extends BaseUpdate {
  adapter: "lolesports_draft" | "grid" | "pandascore";
  patch?: string;
  state: "pending" | "partial" | "final" | "unavailable";
  bluePicks: ChampionPick[];
  redPicks: ChampionPick[];
}

export interface ChampionPick {
  participantId: number;
  championId: string;
  role?: string;
  summonerName?: string;
}

export interface PriceUpdate extends BaseUpdate {
  adapter: "polymarket_clob";
  conditionId: string;
  outcomePrices: Array<{
    outcomeName: string;
    tokenId: string;
    bestBid?: number;
    bestAsk?: number;
    mid?: number;
    spread?: number;
    bidDepth?: number;
    askDepth?: number;
    lastTradePrice?: number;
  }>;
  volume?: number;
  liquidity?: number;
}

export type AdapterUpdate =
  | SourceStatusUpdate
  | GameStateUpdate
  | DraftUpdate
  | PriceUpdate;

export interface DataSourceAdapter<TUpdate extends AdapterUpdate = AdapterUpdate> {
  readonly kind: DataSourceKind;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  subscribe(scope: SubscriptionScope): Promise<SubscriptionHandle>;
  onUpdate(callback: (update: TUpdate) => void): Unsubscribe;
}

export interface SubscriptionHandle {
  id: string;
  scope: SubscriptionScope;
  unsubscribe(): Promise<void>;
}

export type Unsubscribe = () => void;
```

### Initial Adapters

The Phase 1 dashboard adapter set starts with `CitoAdapter` and
`PolymarketAdapter` as the required source adapters. `LoLEsportsDraftAdapter` is
the required draft supplement because the current source decision splits live
game state and picks across Cito and LoLEsports. A future
`PolymarketOrderAdapter` must plug in as another adapter on the same event bus;
it must not require front-end rewrites.

`CitoAdapter`:

- Implements `DataSourceAdapter<GameStateUpdate | SourceStatusUpdate>`.
- Uses Cito schedule/today to list current matches.
- Uses visual-state for subscribed games.
- Writes raw visual-state payloads and normalized snapshots to SQLite.
- Emits explicit failure status for empty live data, auth failures, rate limits,
  schema mismatches, and stale polls.

`LoLEsportsDraftAdapter`:

- Implements `DataSourceAdapter<DraftUpdate | SourceStatusUpdate>`.
- Uses LoLEsports event details/livestats as the draft/picks supplement.
- Writes final or partial draft snapshots to SQLite.
- Does not provide gold/objective authority when Cito data is present.

`PolymarketAdapter`:

- Implements `DataSourceAdapter<PriceUpdate | SourceStatusUpdate>`.
- Discovers or receives mapped Game Winner markets.
- Polls CLOB `/book` for mapped outcome tokens.
- Writes quote snapshots to SQLite.
- Emits skipped/low-confidence status when resolver confidence is below the
  threshold.

### Reserved Third Adapter: Polymarket Order Adapter

Phase 4 can add `PolymarketOrderAdapter` as a separate adapter with kind
`polymarket_order`. It must not change the dashboard front-end contract. In
Phase 1 it is a disabled placeholder type only.

Required boundary:

- no wallet connection in Phase 1;
- no private key storage;
- no real order placement;
- no execution permission UI;
- no strategy-generated order intents.

When Phase 4 is allowed, the order adapter should publish order-system health
and paper/real mode state through the same update bus, but order actions must
remain behind an explicit future issue and review gate.

## 4. Phase 1 Display Content

### Current Matches View

The first screen should be the monitoring dashboard, not a landing page.

Required columns:

- league;
- match start time;
- team names and team codes;
- match state;
- current game number;
- source status for Cito, LoLEsports draft, and Polymarket;
- mapping status and mapping confidence;
- latest update age.

Source: Cito schedule/today for current matches, enriched by local resolver and
stored match/game rows. If Cito schedule is unavailable, the table should show
the last cached rows with an explicit stale/unavailable banner.

### Selected Match Detail

The selected match view should show one game at a time with a compact game
selector for best-of series.

Required live state fields:

- `gameClock`;
- `gameState`;
- blue/red team names and side mapping;
- blue/red gold;
- `goldDiff`;
- objectives: towers, dragons, barons, inhibitors when available;
- kills;
- source observed time and source timestamp;
- source freshness indicator.

The view should distinguish missing fields from zero values. For example, no
baron field from a source is `unavailable`, while a known count of zero is `0`.

### Draft/Picks Panel

Required content:

- blue picks;
- red picks;
- pick state: pending, partial, final, or unavailable;
- patch if available;
- LoLEsports observed time.

This panel is read-only evidence. It should not imply model features or trading
signals.

### Polymarket Price Panel

Required fields:

- Polymarket market title/slug;
- condition ID;
- mapped outcome/team names;
- Yes/No or outcome-token best bid and best ask;
- mid price if both bid and ask are present;
- spread;
- bid/ask depth;
- volume/liquidity when available;
- quote observed time;
- REST polling status or WebSocket status if later enabled.

If there is no high-confidence mapping, show the market under an unmapped or
skipped section. Do not merge it into the selected match detail.

### Historical Snapshot Query

Phase 1 must include a historical snapshot view backed by SQLite.

Minimum filters:

- match;
- game number or game ID;
- source;
- time range;
- limit.

Minimum columns:

- observed time;
- source timestamp;
- game clock;
- game state;
- blue/red gold;
- gold diff;
- objectives summary;
- linked quote snapshot age when a market mapping exists.

The history view should allow copying the raw evidence path or snapshot ID so a
source spike can trace a displayed row back to stored evidence.

## 5. Extension Points

### FairProbabilityEngine Slot

Phase 2 can add a `FairProbabilityEngine` that consumes normalized snapshots and
emits read-only probability estimates:

```ts
export interface FairProbabilityUpdate extends BaseUpdate {
  adapter: "fair_probability";
  modelVersion: string;
  fairWinProbability: {
    blue?: number;
    red?: number;
    mappedPolymarketOutcomes?: Record<string, number>;
  };
  inputsSnapshotId: string;
  warnings: string[];
}
```

Phase 1 should reserve a disabled UI slot labeled by state, not by prediction:

- `not_configured`;
- `waiting_for_engine`;
- `available`;
- `error`.

No Phase 1 code should compute fair probability or emit trade signals.

### Multi-Source Adapter Slot

GRID and PandaScore should fit the same `DataSourceAdapter` interface. They can
produce `GameStateUpdate`, `DraftUpdate`, or both. The dashboard read model
should support source precedence without changing React components:

```text
primary game state source: Cito
draft source: LoLEsports
backup candidates: PandaScore, GRID
future official upgrade: GRID
```

Source precedence belongs in backend configuration, not in the front-end. The UI
should display which source populated each field.

### Polymarket Order Slot

Phase 4 can add an order-system status panel fed by
`PolymarketOrderAdapter`. The front-end should receive order status as an
adapter update, but Phase 1 must not expose order buttons, execution toggles,
wallet forms, private key fields, or trading permission text.

### Test Seams

The adapter interface creates two real adapters from the start: production
adapters and fake adapters used by tests. Tests should exercise behavior through
the interface:

- Cito empty live data emits `unavailable` status and writes no fabricated game
  state.
- Cito visual-state update writes a normalized snapshot and publishes one SSE
  event.
- Polymarket quote update joins only when resolver confidence is at least
  `0.90`.
- Low-confidence mapping appears as skipped and is not merged into match detail.
- Historical query returns rows from SQLite without calling remote APIs.

Risks:

- blocker-now: implementation must not bypass the resolver confidence gate.
- pre-next-card blocker: CAL-53 live loop handoff should confirm the exact
  storage rows the dashboard reads.
- deferred: WebSocket quotes can replace REST polling only after a clean retest
  or explicit source decision.

## 6. Local Run Plan

### Command

The implementation should add one command at the repository root:

```bash
npm run dev:dashboard
```

Recommended behavior:

- starts Fastify API on `127.0.0.1:8787`;
- starts Vite on `127.0.0.1:5173`;
- proxies `/api/*` and `/events/*` from Vite to Fastify;
- uses SQLite path from `PM_LOL_DB_PATH`, defaulting to `data/db/live.db`;
- loads Cito and optional source credentials from environment variables or a
  local `.env` file that is never committed.

### Configuration

Suggested environment variables:

```text
PM_LOL_DB_PATH=data/db/live.db
DASHBOARD_API_HOST=127.0.0.1
DASHBOARD_API_PORT=8787
DASHBOARD_WEB_HOST=127.0.0.1
DASHBOARD_WEB_PORT=5173
CITO_API_KEY=...
LOLESPORTS_API_KEY=...
DASHBOARD_POLL_INTERVAL_SEC=30
POLYMARKET_POLL_INTERVAL_SEC=30
```

`CITO_API_KEY` is required for live Cito calls. The dashboard should still run
without it in cached/read-only mode and clearly mark Cito as `auth_failed` or
`unavailable`.

### API Surface

Minimum backend endpoints:

```text
GET /api/health
GET /api/matches
GET /api/matches/:matchId
GET /api/matches/:matchId/games/:gameId/history
GET /api/sources/status
GET /events/dashboard
```

`/events/dashboard` should use Server-Sent Events for Phase 1. SSE is enough for
one-way live monitoring and is simpler than WebSocket for local read-only
updates. WebSocket can be revisited if bidirectional controls become necessary.

### Acceptance Checklist For Implementation Card

- `npm run dev:dashboard` starts both API and web UI locally.
- The match list renders from Cito schedule/today or cached SQLite rows.
- Selecting a match shows Cito visual-state fields and LoLEsports draft state.
- Polymarket prices show only through high-confidence resolved markets.
- Historical snapshot query reads SQLite.
- Every panel shows source status and freshness.
- No strategy, prediction, signal, wallet, private key, or order-placement code
  exists in Phase 1.
