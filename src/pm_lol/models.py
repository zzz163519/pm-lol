from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Market:
    market_id: str
    condition_id: str
    slug: str
    title: str
    outcomes: list[str]
    token_ids: list[str]
    volume: float | None = None
    liquidity: float | None = None
    active: bool = True
    closed: bool = False
    event_id: str | None = None
    event_slug: str | None = None
    question_id: str | None = None
    market_type: str = "game_winner"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QuoteSnapshot:
    condition_id: str
    token_id: str
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    bid_depth: float
    ask_depth: float
    timestamp_ms: int | None = None
    bids: list[dict[str, str]] = field(default_factory=list)
    asks: list[dict[str, str]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Match:
    match_id: str
    league: str | None
    team_a_id: str
    team_a_name: str
    team_b_id: str
    team_b_name: str
    start_time: str | None = None
    state: str | None = None
    strategy_type: str | None = None
    strategy_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Game:
    game_id: str
    match_id: str
    game_number: int
    blue_team_id: str
    red_team_id: str
    state: str
    patch: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GameStateSnapshot:
    game_id: str
    timestamp: str
    game_state: str
    blue_gold: int
    red_gold: int
    blue_towers: int
    red_towers: int
    blue_dragons: list[str]
    red_dragons: list[str]
    blue_barons: int
    red_barons: int
    blue_kills: int
    red_kills: int
    game_clock: float | None = None
    # None means "unknown / unobserved" — never inferred as False. Cito visual
    # state and LoLEsports livestats windows do not report a reliable pause flag,
    # so an absent value stays None (stored as NULL) rather than a hardcoded 0.
    paused: bool | None = None
    source_status: str = "ok"
    sample_age_seconds: int | None = None
    rate_limit_state: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    source: str = "lolesports_livestats_window"
    winner: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DraftSnapshot:
    game_id: str
    team_id: str
    participant_id: int
    champion_id: str
    role: str
    summoner_name: str
    match_id: str | None = None
    patch: str | None = None
    side: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedMarket:
    market_id: str
    condition_id: str
    match_id: str
    game_id: str
    game_number: int
    team_a: str
    team_b: str
    blue_team_id: str
    red_team_id: str
    mapping_confidence: float
    market_type: str = "game_winner"
    market_status: str = "resolved"
