from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pm_lol.models import DraftSnapshot, Game, GameStateSnapshot, Market, Match, QuoteSnapshot


class SQLiteStorage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def list_tables(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return [row["name"] for row in rows]

    def upsert_market(self, market: Market) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO markets (
                    market_id, condition_id, question_id, event_id, event_slug,
                    slug, title, market_type, outcomes_json, token_ids_json,
                    yes_token_id, no_token_id, volume, liquidity, active, closed,
                    raw_json, source, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market_id) DO UPDATE SET
                    condition_id = excluded.condition_id,
                    slug = excluded.slug,
                    title = excluded.title,
                    outcomes_json = excluded.outcomes_json,
                    token_ids_json = excluded.token_ids_json,
                    volume = excluded.volume,
                    liquidity = excluded.liquidity,
                    active = excluded.active,
                    closed = excluded.closed,
                    updated_at = excluded.updated_at
                """,
                (
                    market.market_id,
                    market.condition_id,
                    market.question_id,
                    market.event_id,
                    market.event_slug,
                    market.slug,
                    market.title,
                    market.market_type,
                    json.dumps(market.outcomes),
                    json.dumps(market.token_ids),
                    market.token_ids[0] if market.token_ids else None,
                    market.token_ids[1] if len(market.token_ids) > 1 else None,
                    market.volume,
                    market.liquidity,
                    int(market.active),
                    int(market.closed),
                    json.dumps(market.raw),
                    "polymarket_gamma",
                    1.0,
                    now,
                    now,
                ),
            )

    def get_market(self, market_id: str) -> Market:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM markets WHERE market_id = ?",
                (market_id,),
            ).fetchone()
        if row is None:
            raise KeyError(market_id)
        return Market(
            market_id=row["market_id"],
            condition_id=row["condition_id"],
            question_id=row["question_id"],
            event_id=row["event_id"],
            event_slug=row["event_slug"],
            slug=row["slug"],
            title=row["title"],
            market_type=row["market_type"],
            outcomes=json.loads(row["outcomes_json"]),
            token_ids=json.loads(row["token_ids_json"]),
            volume=row["volume"],
            liquidity=row["liquidity"],
            active=bool(row["active"]),
            closed=bool(row["closed"]),
            raw=json.loads(row["raw_json"]),
        )

    def list_markets(self) -> list[Market]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM markets ORDER BY market_id").fetchall()
        return [self._market_from_row(row) for row in rows]

    def insert_quote(self, quote: QuoteSnapshot) -> None:
        now = _now()
        quote_id = f"{quote.condition_id}:{quote.token_id}:{quote.timestamp_ms or now}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO quotes (
                    quote_id, condition_id, token_id, best_bid, best_ask, spread,
                    bid_depth, ask_depth, bids_json, asks_json, source_timestamp_ms,
                    observed_at, raw_json, source, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    quote.condition_id,
                    quote.token_id,
                    quote.best_bid,
                    quote.best_ask,
                    quote.spread,
                    quote.bid_depth,
                    quote.ask_depth,
                    json.dumps(quote.bids),
                    json.dumps(quote.asks),
                    quote.timestamp_ms,
                    now,
                    json.dumps(quote.raw),
                    "polymarket_clob_rest",
                    1.0,
                    now,
                ),
            )

    def get_latest_quote(self, condition_id: str, token_id: str) -> QuoteSnapshot:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM quotes
                WHERE condition_id = ? AND token_id = ?
                ORDER BY observed_at DESC
                LIMIT 1
                """,
                (condition_id, token_id),
            ).fetchone()
        if row is None:
            raise KeyError((condition_id, token_id))
        return QuoteSnapshot(
            condition_id=row["condition_id"],
            token_id=row["token_id"],
            best_bid=row["best_bid"],
            best_ask=row["best_ask"],
            spread=row["spread"],
            bid_depth=row["bid_depth"],
            ask_depth=row["ask_depth"],
            timestamp_ms=row["source_timestamp_ms"],
            bids=json.loads(row["bids_json"]),
            asks=json.loads(row["asks_json"]),
            raw=json.loads(row["raw_json"]),
        )

    def upsert_match(self, match: Match) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO matches (
                    match_id, league, team_a_id, team_a_name, team_b_id, team_b_name,
                    start_time, state, strategy_type, strategy_count, raw_json,
                    source, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    league = excluded.league,
                    state = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (
                    match.match_id,
                    match.league,
                    match.team_a_id,
                    match.team_a_name,
                    match.team_b_id,
                    match.team_b_name,
                    match.start_time,
                    match.state,
                    match.strategy_type,
                    match.strategy_count,
                    json.dumps(match.raw),
                    "lolesports_event_details",
                    1.0,
                    now,
                    now,
                ),
            )

    def list_matches(self) -> list[Match]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM matches ORDER BY match_id").fetchall()
        return [
            Match(
                match_id=row["match_id"],
                league=row["league"],
                team_a_id=row["team_a_id"],
                team_a_name=row["team_a_name"],
                team_b_id=row["team_b_id"],
                team_b_name=row["team_b_name"],
                start_time=row["start_time"],
                state=row["state"],
                strategy_type=row["strategy_type"],
                strategy_count=row["strategy_count"],
                raw=json.loads(row["raw_json"]),
            )
            for row in rows
        ]

    def upsert_game(self, game: Game) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO games (
                    game_id, match_id, game_number, blue_team_id, red_team_id,
                    state, patch, raw_json, source, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    state = excluded.state,
                    patch = excluded.patch,
                    updated_at = excluded.updated_at
                """,
                (
                    game.game_id,
                    game.match_id,
                    game.game_number,
                    game.blue_team_id,
                    game.red_team_id,
                    game.state,
                    game.patch,
                    json.dumps(game.raw),
                    "lolesports_event_details",
                    1.0,
                    now,
                    now,
                ),
            )

    def list_games_for_match(self, match_id: str) -> list[Game]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM games WHERE match_id = ? ORDER BY game_number",
                (match_id,),
            ).fetchall()
        return [
            Game(
                game_id=row["game_id"],
                match_id=row["match_id"],
                game_number=row["game_number"],
                blue_team_id=row["blue_team_id"],
                red_team_id=row["red_team_id"],
                state=row["state"],
                patch=row["patch"],
                raw=json.loads(row["raw_json"]),
            )
            for row in rows
        ]

    def insert_game_state_snapshot(self, snapshot: GameStateSnapshot) -> None:
        now = _now()
        snapshot_id = f"{snapshot.game_id}:{snapshot.timestamp}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO game_state_snapshots (
                    snapshot_id, game_id, game_clock, observed_at, source_timestamp,
                    game_state, blue_gold, red_gold, gold_diff, blue_towers, red_towers,
                    blue_dragons, red_dragons, blue_dragons_json, red_dragons_json,
                    blue_barons, red_barons, blue_kills, red_kills, blue_inhibitors,
                    red_inhibitors, paused, finished, winner, participants_json, raw_json,
                    source_status, sample_age_seconds, rate_limit_state, error_code,
                    source, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot.game_id,
                    snapshot.game_clock,
                    now,
                    snapshot.timestamp,
                    snapshot.game_state,
                    snapshot.blue_gold,
                    snapshot.red_gold,
                    snapshot.blue_gold - snapshot.red_gold,
                    snapshot.blue_towers,
                    snapshot.red_towers,
                    len(snapshot.blue_dragons),
                    len(snapshot.red_dragons),
                    json.dumps(snapshot.blue_dragons),
                    json.dumps(snapshot.red_dragons),
                    snapshot.blue_barons,
                    snapshot.red_barons,
                    snapshot.blue_kills,
                    snapshot.red_kills,
                    snapshot.raw.get("blueTeam", {}).get("inhibitors"),
                    snapshot.raw.get("redTeam", {}).get("inhibitors"),
                    _paused_to_db(snapshot.paused),
                    int(snapshot.game_state in {"finished", "completed"}),
                    snapshot.winner,
                    json.dumps(
                        {
                            "blue": snapshot.raw.get("blueTeam", {}).get("participants", []),
                            "red": snapshot.raw.get("redTeam", {}).get("participants", []),
                        }
                    ),
                    json.dumps(snapshot.raw),
                    snapshot.source_status,
                    snapshot.sample_age_seconds,
                    json.dumps(snapshot.rate_limit_state),
                    snapshot.error_code,
                    snapshot.source,
                    1.0,
                    now,
                ),
            )

    def get_game_state_snapshots(self, game_id: str) -> list[GameStateSnapshot]:
        """Read game-state snapshots back for replay/query.

        ``paused`` round-trips as a tri-state: NULL -> None (unknown),
        1 -> True, 0 -> False. It is never coerced to a hardcoded boolean.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    game_id, source_timestamp, game_state, game_clock,
                    blue_gold, red_gold, blue_towers, red_towers,
                    blue_dragons_json, red_dragons_json, blue_barons, red_barons,
                    blue_kills, red_kills, source_status, sample_age_seconds,
                    rate_limit_state, error_code, source, winner, paused, raw_json
                FROM game_state_snapshots
                WHERE game_id = ?
                ORDER BY source_timestamp ASC
                """,
                (game_id,),
            ).fetchall()
        return [
            GameStateSnapshot(
                game_id=row["game_id"],
                timestamp=row["source_timestamp"],
                game_state=row["game_state"],
                blue_gold=row["blue_gold"],
                red_gold=row["red_gold"],
                blue_towers=row["blue_towers"],
                red_towers=row["red_towers"],
                blue_dragons=json.loads(row["blue_dragons_json"]),
                red_dragons=json.loads(row["red_dragons_json"]),
                blue_barons=row["blue_barons"],
                red_barons=row["red_barons"],
                blue_kills=row["blue_kills"],
                red_kills=row["red_kills"],
                game_clock=row["game_clock"],
                source_status=row["source_status"],
                sample_age_seconds=row["sample_age_seconds"],
                rate_limit_state=json.loads(row["rate_limit_state"]),
                error_code=row["error_code"],
                source=row["source"],
                winner=row["winner"],
                paused=_paused_from_db(row["paused"]),
                raw=json.loads(row["raw_json"]),
            )
            for row in rows
        ]

    def insert_draft_snapshot(
        self,
        draft: DraftSnapshot,
        blue_team_id: str,
        red_team_id: str,
        blue_champions: list[str],
        red_champions: list[str],
    ) -> None:
        now = _now()
        snapshot_id = f"{draft.game_id}:{draft.participant_id}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO draft_snapshots (
                    draft_snapshot_id, match_id, game_id, patch, team_id, team_side,
                    participant_id, esports_player_id, champion_id, role, summoner_name,
                    blue_team_id, red_team_id, blue_champions_json, red_champions_json,
                    bans_json, draft_complete, observed_at, raw_json, source,
                    confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    draft.match_id,
                    draft.game_id,
                    draft.patch,
                    draft.team_id,
                    draft.side,
                    draft.participant_id,
                    draft.raw.get("esportsPlayerId"),
                    draft.champion_id,
                    draft.role,
                    draft.summoner_name,
                    blue_team_id,
                    red_team_id,
                    json.dumps(blue_champions),
                    json.dumps(red_champions),
                    None,
                    int(len(blue_champions) == 5 and len(red_champions) == 5),
                    now,
                    json.dumps(draft.raw),
                    "lolesports_livestats_window_metadata",
                    1.0,
                    now,
                ),
            )

    def insert_resolved_market_attempt(
        self,
        market: Market,
        match: Match,
        game: Game,
        mapping_confidence: float,
        market_status: str,
        skip_reason: str | None,
    ) -> None:
        now = _now()
        resolved_market_id = f"{market.market_id}:{game.game_id}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO resolved_markets (
                    resolved_market_id, market_id, condition_id, yes_token_id, no_token_id,
                    league, match_id, game_id, game_number, team_a_id, team_b_id,
                    team_a_name, team_b_name, blue_team_id, red_team_id, market_type,
                    mapping_confidence, market_status, skip_reason, raw_mapping_json,
                    source, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_market_id,
                    market.market_id,
                    market.condition_id,
                    market.token_ids[0],
                    market.token_ids[1],
                    match.league,
                    match.match_id,
                    game.game_id,
                    game.game_number,
                    match.team_a_id,
                    match.team_b_id,
                    match.team_a_name,
                    match.team_b_name,
                    game.blue_team_id,
                    game.red_team_id,
                    market.market_type,
                    mapping_confidence,
                    market_status,
                    skip_reason,
                    json.dumps(
                        {
                            "market_outcomes": market.outcomes,
                            "match_teams": [match.team_a_name, match.team_b_name],
                        }
                    ),
                    "market_match_resolver",
                    mapping_confidence,
                    now,
                    now,
                ),
            )

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _market_from_row(self, row: sqlite3.Row) -> Market:
        return Market(
            market_id=row["market_id"],
            condition_id=row["condition_id"],
            question_id=row["question_id"],
            event_id=row["event_id"],
            event_slug=row["event_slug"],
            slug=row["slug"],
            title=row["title"],
            market_type=row["market_type"],
            outcomes=json.loads(row["outcomes_json"]),
            token_ids=json.loads(row["token_ids_json"]),
            volume=row["volume"],
            liquidity=row["liquidity"],
            active=bool(row["active"]),
            closed=bool(row["closed"]),
            raw=json.loads(row["raw_json"]),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    condition_id TEXT NOT NULL UNIQUE,
    question_id TEXT,
    event_id TEXT,
    event_slug TEXT,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    market_type TEXT NOT NULL,
    outcomes_json TEXT NOT NULL,
    token_ids_json TEXT NOT NULL,
    yes_token_id TEXT,
    no_token_id TEXT,
    volume REAL,
    liquidity REAL,
    active INTEGER NOT NULL,
    closed INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    league TEXT,
    league_id TEXT,
    league_slug TEXT,
    team_a_id TEXT NOT NULL,
    team_a_name TEXT NOT NULL,
    team_a_code TEXT,
    team_b_id TEXT NOT NULL,
    team_b_name TEXT NOT NULL,
    team_b_code TEXT,
    start_time TEXT,
    state TEXT,
    strategy_type TEXT,
    strategy_count INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    game_number INTEGER NOT NULL,
    blue_team_id TEXT NOT NULL,
    red_team_id TEXT NOT NULL,
    state TEXT NOT NULL,
    start_time TEXT,
    patch TEXT,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(match_id, game_number)
);

CREATE TABLE IF NOT EXISTS resolved_markets (
    resolved_market_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    condition_id TEXT NOT NULL,
    yes_token_id TEXT NOT NULL,
    no_token_id TEXT NOT NULL,
    league TEXT,
    match_id TEXT NOT NULL,
    game_id TEXT NOT NULL,
    game_number INTEGER NOT NULL,
    team_a_id TEXT,
    team_b_id TEXT,
    team_a_name TEXT NOT NULL,
    team_b_name TEXT NOT NULL,
    blue_team_id TEXT NOT NULL,
    red_team_id TEXT NOT NULL,
    blue_team_name TEXT,
    red_team_name TEXT,
    market_type TEXT NOT NULL,
    mapping_confidence REAL NOT NULL,
    market_status TEXT NOT NULL,
    skip_reason TEXT,
    raw_mapping_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(market_id, game_id)
);

CREATE TABLE IF NOT EXISTS quotes (
    quote_id TEXT PRIMARY KEY,
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    bid_depth REAL NOT NULL,
    ask_depth REAL NOT NULL,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    last_trade_price REAL,
    min_order_size REAL,
    tick_size REAL,
    neg_risk INTEGER,
    source_timestamp_ms INTEGER,
    observed_at TEXT NOT NULL,
    source_latency_sec REAL,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(game_id),
    game_clock REAL,
    observed_at TEXT NOT NULL,
    source_timestamp TEXT NOT NULL,
    source_latency_sec REAL,
    game_state TEXT NOT NULL,
    blue_gold INTEGER NOT NULL,
    red_gold INTEGER NOT NULL,
    gold_diff INTEGER NOT NULL,
    blue_towers INTEGER NOT NULL,
    red_towers INTEGER NOT NULL,
    blue_dragons INTEGER NOT NULL,
    red_dragons INTEGER NOT NULL,
    blue_dragons_json TEXT NOT NULL,
    red_dragons_json TEXT NOT NULL,
    first_dragon_team TEXT,
    blue_barons INTEGER NOT NULL,
    red_barons INTEGER NOT NULL,
    baron_status TEXT,
    elder_status TEXT,
    blue_kills INTEGER NOT NULL,
    red_kills INTEGER NOT NULL,
    blue_inhibitors INTEGER,
    red_inhibitors INTEGER,
    paused INTEGER,
    finished INTEGER NOT NULL,
    winner TEXT,
    participants_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'ok',
    sample_age_seconds INTEGER,
    rate_limit_state TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(game_id, source_timestamp)
);

CREATE TABLE IF NOT EXISTS draft_snapshots (
    draft_snapshot_id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    game_id TEXT NOT NULL REFERENCES games(game_id),
    patch TEXT,
    team_id TEXT NOT NULL,
    team_side TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    esports_player_id TEXT,
    champion_id TEXT NOT NULL,
    role TEXT NOT NULL,
    summoner_name TEXT NOT NULL,
    blue_team_id TEXT NOT NULL,
    red_team_id TEXT NOT NULL,
    blue_champions_json TEXT NOT NULL,
    red_champions_json TEXT NOT NULL,
    bans_json TEXT,
    draft_complete INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    source_timestamp TEXT,
    source_latency_sec REAL,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(game_id, participant_id, observed_at)
);
"""


def _paused_to_db(paused: bool | None) -> int | None:
    """Serialize the tri-state pause flag: None -> NULL (unknown), else 0/1.

    Deliberately does NOT collapse ``None`` to ``0`` — an unproven pause state
    must persist as unknown, not a fabricated ``not paused``.
    """
    if paused is None:
        return None
    return int(paused)


def _paused_from_db(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)
