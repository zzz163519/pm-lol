import json
from pathlib import Path

from pm_lol.collectors.polymarket_quote_recorder import (
    QuoteTarget,
    PolymarketQuoteRecorder,
)
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"
TOKEN_ID = "100172814846746500028191734405612966589475835807067790171955690167538278072521"
OTHER_TOKEN_ID = "45237782937761666957430863754762402074289825813292595850496859818516586364597"
CONDITION_ID = "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553"


class FakeBookClient:
    def get_orderbook(self, token_id):
        books = json.loads((FIXTURES / "polymarket-orderbook-sample.json").read_text())
        return next(book for book in books if book["asset_id"] == token_id)


class FakeRetryableError(Exception):
    status_code = 429


def test_quote_recorder_writes_orderbook_snapshot(tmp_path):
    storage = SQLiteStorage(tmp_path / "quotes.db")
    recorder = PolymarketQuoteRecorder(FakeBookClient(), storage, [TOKEN_ID])

    summary = recorder.run_once()
    quote = storage.get_latest_quote(
        "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553",
        TOKEN_ID,
    )

    assert summary == {
        "tokens_seen": 1,
        "quotes_written": 1,
        "skipped": 0,
        "errors": 0,
    }
    assert quote.best_bid == 0.791
    assert quote.best_ask == 0.801
    assert quote.spread == 0.01


def test_quote_recorder_writes_market_context_status_and_outcome(tmp_path):
    storage = SQLiteStorage(tmp_path / "quotes.db")
    target = QuoteTarget(
        event_slug="lol-ktc-sgw-2026-06-15",
        market_slug="lol-ktc-sgw-2026-06-15-game2",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        outcome="KT Rolster Challengers",
    )
    recorder = PolymarketQuoteRecorder(FakeBookClient(), storage, [target])

    summary = recorder.run_once()
    rows = storage.query_quotes(market_slug="lol-ktc-sgw-2026-06-15-game2")

    assert summary == {
        "tokens_seen": 1,
        "quotes_written": 1,
        "skipped": 0,
        "errors": 0,
    }
    assert len(rows) == 1
    assert rows[0]["event_slug"] == "lol-ktc-sgw-2026-06-15"
    assert rows[0]["market_slug"] == "lol-ktc-sgw-2026-06-15-game2"
    assert rows[0]["condition_id"] == CONDITION_ID
    assert rows[0]["token_id"] == TOKEN_ID
    assert rows[0]["outcome"] == "KT Rolster Challengers"
    assert rows[0]["bid_count"] == 36
    assert rows[0]["ask_count"] == 17
    assert rows[0]["source_status"] == "ok"
    assert rows[0]["error_code"] is None


def test_quote_recorder_records_empty_book_as_no_liquidity(tmp_path):
    class EmptyBookClient:
        def get_orderbook(self, token_id):
            return {
                "market": CONDITION_ID,
                "asset_id": token_id,
                "timestamp": "1781508217535",
                "bids": [],
                "asks": [],
            }

    storage = SQLiteStorage(tmp_path / "quotes.db")
    target = QuoteTarget(
        event_slug="lol-ktc-sgw-2026-06-15",
        market_slug="lol-ktc-sgw-2026-06-15-game5",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        outcome="KT Rolster Challengers",
    )
    recorder = PolymarketQuoteRecorder(EmptyBookClient(), storage, [target])

    summary = recorder.run_once()
    row = storage.query_quotes(market_slug="lol-ktc-sgw-2026-06-15-game5")[0]

    assert summary == {
        "tokens_seen": 1,
        "quotes_written": 1,
        "skipped": 0,
        "errors": 0,
    }
    assert row["best_bid"] is None
    assert row["best_ask"] is None
    assert row["bid_count"] == 0
    assert row["ask_count"] == 0
    assert row["source_status"] == "no_liquidity"
    assert row["error_code"] is None


def test_quote_recorder_records_missing_market_as_absent_without_client_call(tmp_path):
    class ExplodingClient:
        def get_orderbook(self, token_id):
            raise AssertionError("absent targets should not request orderbooks")

    storage = SQLiteStorage(tmp_path / "quotes.db")
    target = QuoteTarget(
        event_slug="lol-ktc-sgw-2026-06-15",
        market_slug="lol-ktc-sgw-2026-06-15-game5",
        condition_id=None,
        token_id=None,
        outcome=None,
    )
    recorder = PolymarketQuoteRecorder(ExplodingClient(), storage, [target])

    summary = recorder.run_once()
    row = storage.query_quotes(market_slug="lol-ktc-sgw-2026-06-15-game5")[0]

    assert summary == {
        "tokens_seen": 1,
        "quotes_written": 1,
        "skipped": 1,
        "errors": 0,
    }
    assert row["condition_id"] is None
    assert row["token_id"] is None
    assert row["source_status"] == "absent"
    assert row["error_code"] == "missing_market"


def test_quote_recorder_retries_429_then_records_recovered_snapshot(tmp_path):
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def get_orderbook(self, token_id):
            self.calls += 1
            if self.calls == 1:
                raise FakeRetryableError("too many requests")
            return FakeBookClient().get_orderbook(token_id)

    client = FlakyClient()
    storage = SQLiteStorage(tmp_path / "quotes.db")
    target = QuoteTarget(
        event_slug="lol-ktc-sgw-2026-06-15",
        market_slug="lol-ktc-sgw-2026-06-15-game2",
        condition_id=CONDITION_ID,
        token_id=TOKEN_ID,
        outcome="KT Rolster Challengers",
    )
    recorder = PolymarketQuoteRecorder(client, storage, [target], max_attempts=2, sleep=lambda _: None)

    summary = recorder.run_once()
    row = storage.query_quotes(token_id=TOKEN_ID)[0]

    assert client.calls == 2
    assert summary["quotes_written"] == 1
    assert summary["errors"] == 0
    assert row["source_status"] == "ok"
    assert row["error_code"] is None


def test_quote_recorder_classifies_exhausted_5xx_as_error(tmp_path):
    class ServerError(Exception):
        status_code = 503

    class FailingClient:
        def __init__(self):
            self.calls = 0

        def get_orderbook(self, token_id):
            self.calls += 1
            raise ServerError("service unavailable")

    client = FailingClient()
    storage = SQLiteStorage(tmp_path / "quotes.db")
    target = QuoteTarget(
        event_slug="lol-ktc-sgw-2026-06-15",
        market_slug="lol-ktc-sgw-2026-06-15-game2",
        condition_id=CONDITION_ID,
        token_id=OTHER_TOKEN_ID,
        outcome="Saigon Warriors",
    )
    recorder = PolymarketQuoteRecorder(client, storage, [target], max_attempts=2, sleep=lambda _: None)

    summary = recorder.run_once()
    row = storage.query_quotes(token_id=OTHER_TOKEN_ID)[0]

    assert client.calls == 2
    assert summary == {
        "tokens_seen": 1,
        "quotes_written": 1,
        "skipped": 0,
        "errors": 1,
    }
    assert row["source_status"] == "error"
    assert row["error_code"] == "http_503"


def test_quote_query_filters_by_market_game_and_time_range(tmp_path):
    storage = SQLiteStorage(tmp_path / "quotes.db")
    recorder = PolymarketQuoteRecorder(
        FakeBookClient(),
        storage,
        [
            QuoteTarget(
                event_slug="lol-ktc-sgw-2026-06-15",
                market_slug="lol-ktc-sgw-2026-06-15-game2",
                condition_id=CONDITION_ID,
                token_id=TOKEN_ID,
                outcome="KT Rolster Challengers",
                game_number=2,
            ),
            QuoteTarget(
                event_slug="lol-ktc-sgw-2026-06-15",
                market_slug="lol-ktc-sgw-2026-06-15-game2",
                condition_id=CONDITION_ID,
                token_id=OTHER_TOKEN_ID,
                outcome="Saigon Warriors",
                game_number=2,
            ),
        ],
    )
    recorder.run_once()

    rows = storage.query_quotes(
        market_slug="lol-ktc-sgw-2026-06-15-game2",
        game_number=2,
        observed_from="2000-01-01T00:00:00+00:00",
        observed_to="2999-01-01T00:00:00+00:00",
    )

    assert [row["outcome"] for row in rows] == ["KT Rolster Challengers", "Saigon Warriors"]
    assert all(row["game_number"] == 2 for row in rows)
    assert all(row["observed_at"] for row in rows)


def test_quote_recorder_does_not_import_wallet_or_order_modules():
    forbidden_import_fragments = [
        "wallet",
        "private_key",
        "broker",
        "trade",
        "clob_client",
    ]
    source = Path("src/pm_lol/collectors/polymarket_quote_recorder.py").read_text()
    import_lines = [
        line.lower()
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]

    assert not any(
        fragment in line
        for line in import_lines
        for fragment in forbidden_import_fragments
    )
    assert "create_order" not in source
    assert "post_order" not in source
    assert "place_order" not in source
