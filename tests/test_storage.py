from pm_lol.models import Market, QuoteSnapshot
from pm_lol.storage import SQLiteStorage


def test_storage_creates_expected_tables(tmp_path):
    db_path = tmp_path / "pm_lol.sqlite3"
    storage = SQLiteStorage(db_path)

    tables = storage.list_tables()

    assert {
        "markets",
        "resolved_markets",
        "quotes",
        "matches",
        "games",
        "game_state_snapshots",
        "draft_snapshots",
    }.issubset(set(tables))


def test_storage_roundtrips_market_and_quote(tmp_path):
    db_path = tmp_path / "pm_lol.sqlite3"
    storage = SQLiteStorage(db_path)

    market = Market(
        market_id="2530922",
        condition_id="0x56243f",
        slug="lol-ktc-sgw-2026-06-15-game2",
        title="Game 2 Winner",
        outcomes=["KT Rolster Challengers", "Saigon Warriors"],
        token_ids=["100172", "452377"],
        volume=74955.37,
        liquidity=13334.03,
    )
    storage.upsert_market(market)
    loaded_market = storage.get_market("2530922")

    quote = QuoteSnapshot(
        condition_id="0x56243f",
        token_id="100172",
        best_bid=0.791,
        best_ask=0.801,
        spread=0.01,
        bid_depth=100.0,
        ask_depth=90.0,
        timestamp_ms=1781508217535,
    )
    storage.insert_quote(quote)
    loaded_quote = storage.get_latest_quote("0x56243f", "100172")

    assert loaded_market.market_id == market.market_id
    assert loaded_market.condition_id == market.condition_id
    assert loaded_quote.token_id == quote.token_id
    assert loaded_quote.best_bid == quote.best_bid
