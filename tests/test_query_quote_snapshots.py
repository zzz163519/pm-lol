import json
from pathlib import Path

from pm_lol.collectors.polymarket_quote_recorder import (
    QuoteTarget,
    PolymarketQuoteRecorder,
)
from pm_lol.storage import SQLiteStorage
from scripts.query_quote_snapshots import main


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"
TOKEN_ID = "100172814846746500028191734405612966589475835807067790171955690167538278072521"
CONDITION_ID = "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553"


class FakeBookClient:
    def get_orderbook(self, token_id):
        books = json.loads((FIXTURES / "polymarket-orderbook-sample.json").read_text())
        return next(book for book in books if book["asset_id"] == token_id)


def test_query_quote_snapshots_outputs_filtered_json(tmp_path, capsys):
    db_path = tmp_path / "quotes.db"
    storage = SQLiteStorage(db_path)
    PolymarketQuoteRecorder(
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
            )
        ],
    ).run_once()

    exit_code = main(
        [
            "--db",
            str(db_path),
            "--market-slug",
            "lol-ktc-sgw-2026-06-15-game2",
            "--game-number",
            "2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["count"] == 1
    assert payload["quotes"][0]["token_id"] == TOKEN_ID
    assert payload["quotes"][0]["source_status"] == "ok"
