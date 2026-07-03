import json
from pathlib import Path

from pm_lol.collectors.polymarket_quote_recorder import PolymarketQuoteRecorder
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"
TOKEN_ID = "100172814846746500028191734405612966589475835807067790171955690167538278072521"


class FakeBookClient:
    def get_orderbook(self, token_id):
        books = json.loads((FIXTURES / "polymarket-orderbook-sample.json").read_text())
        return next(book for book in books if book["asset_id"] == token_id)


def test_quote_recorder_writes_orderbook_snapshot(tmp_path):
    storage = SQLiteStorage(tmp_path / "quotes.db")
    recorder = PolymarketQuoteRecorder(FakeBookClient(), storage, [TOKEN_ID])

    summary = recorder.run_once()
    quote = storage.get_latest_quote(
        "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553",
        TOKEN_ID,
    )

    assert summary == {"tokens_seen": 1, "quotes_written": 1}
    assert quote.best_bid == 0.791
    assert quote.best_ask == 0.801
    assert quote.spread == 0.01
