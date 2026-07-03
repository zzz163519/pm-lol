import sqlite3

from pm_lol.models import Game, Market, Match
from pm_lol.resolvers.market_match_resolver import (
    resolve_market_to_game,
    resolve_pending_markets,
    team_name_confidence,
)
from pm_lol.storage import SQLiteStorage


def test_team_name_confidence_matches_common_alias():
    assert team_name_confidence("KT", "kt-rolster") >= 0.9


def test_resolver_maps_market_to_game_when_confidence_is_high():
    market = Market(
        market_id="2530922",
        condition_id="0x56243f",
        slug="lol-ktc-sgw-2026-06-15-game2",
        title="LoL: KT Rolster Challengers vs Saigon Warriors - Game 2 Winner",
        outcomes=["KT", "Saigon Warriors"],
        token_ids=["100172", "452377"],
    )
    match = Match(
        match_id="match-1",
        league="Asia Masters",
        team_a_id="ktc",
        team_a_name="kt-rolster",
        team_b_id="sgw",
        team_b_name="Saigon Warriors",
    )
    game = Game(
        game_id="game-2",
        match_id="match-1",
        game_number=2,
        blue_team_id="ktc",
        red_team_id="sgw",
        state="unstarted",
    )

    resolved = resolve_market_to_game(market, match, [game])

    assert resolved is not None
    assert resolved.market_id == "2530922"
    assert resolved.game_id == "game-2"
    assert resolved.game_number == 2
    assert resolved.blue_team_id == "ktc"
    assert resolved.red_team_id == "sgw"
    assert resolved.mapping_confidence >= 0.9


def test_resolver_skips_low_confidence_market():
    market = Market(
        market_id="bad-market",
        condition_id="0xbad",
        slug="lol-abc-def-game1",
        title="LoL: Unknown Team vs Other Team - Game 1 Winner",
        outcomes=["Unknown Team", "Other Team"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )

    assert resolve_market_to_game(market, match, [game]) is None


def test_resolve_pending_markets_writes_high_confidence_mapping(tmp_path):
    db_path = tmp_path / "resolver.db"
    storage = SQLiteStorage(db_path)
    market = Market(
        market_id="m1",
        condition_id="0xmatch",
        slug="lol-t1-gen-2026-06-14-game1",
        title="LoL: T1 vs Gen.G Esports - Game 1 Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )
    storage.upsert_market(market)
    storage.upsert_match(match)
    storage.upsert_game(game)

    summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT mapping_confidence, market_status FROM resolved_markets WHERE market_id = 'm1'"
        ).fetchone()

    assert summary == {"markets_seen": 1, "resolved": 1, "skipped": 0}
    assert row[0] >= 0.9
    assert row[1] == "active"
