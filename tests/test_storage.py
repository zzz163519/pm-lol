import pytest

from pm_lol.models import CollectorRunEvent, Market, QuoteSnapshot
from pm_lol.storage import CANONICAL_SOURCE_STATUSES, SCHEMA_VERSION
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
        "collector_runs",
        "schema_metadata",
    }.issubset(set(tables))


def test_storage_exposes_schema_version_and_canonical_source_statuses(tmp_path):
    storage = SQLiteStorage(tmp_path / "pm_lol.sqlite3")

    assert storage.get_schema_version() == SCHEMA_VERSION
    assert {
        "ok",
        "partial",
        "missing_field",
        "stale",
        "rate_limited",
        "auth_required",
        "network_error",
        "parse_error",
        "skipped_low_confidence",
        "no_liquidity",
        "absent",
    }.issubset(CANONICAL_SOURCE_STATUSES)

    with pytest.raises(ValueError, match="unknown source_status"):
        storage.record_collector_run_event(
            CollectorRunEvent(
                run_id="run-bad",
                collector_name="fixture",
                source="fixture",
                target="game-1",
                source_status="made_up_status",
                outcome="failed",
            )
        )


def test_storage_records_collector_run_events_for_report_timeline(tmp_path):
    storage = SQLiteStorage(tmp_path / "pm_lol.sqlite3")

    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="run-1",
            collector_name="polymarket_quote_recorder",
            source="polymarket_clob_rest",
            target="condition:token",
            source_status="ok",
            outcome="snapshot_written",
            records_read=1,
            records_written=1,
            budget_state={"remaining": 5},
        )
    )
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="run-2",
            collector_name="live_game_state_connector",
            source="cito_visual_state",
            target="game-1",
            source_status="rate_limited",
            outcome="skipped",
            error_code="http_429",
            budget_state={"backoff_seconds": 60},
        )
    )

    events = storage.list_collector_run_events()

    assert [event["run_id"] for event in events] == ["run-1", "run-2"]
    assert events[0]["source_schema_version"] == SCHEMA_VERSION
    assert events[0]["budget_state"] == {"remaining": 5}
    assert events[1]["source_status"] == "rate_limited"
    assert events[1]["error_code"] == "http_429"


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
