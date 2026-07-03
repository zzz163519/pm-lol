import json
from pathlib import Path

from pm_lol.collectors.polymarket_market_collector import PolymarketMarketCollector
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


class FakeMarketClient:
    def search_markets(self, keywords):
        payload = json.loads((FIXTURES / "polymarket-market-sample.json").read_text())
        return [payload]


def test_market_collector_writes_active_game_winner_market(tmp_path):
    storage = SQLiteStorage(tmp_path / "collector.db")
    collector = PolymarketMarketCollector(FakeMarketClient(), storage)

    summary = collector.run_once()
    market = storage.get_market("2530922")

    assert summary == {"markets_seen": 1, "markets_written": 1, "active_token_ids": 2}
    assert market.condition_id == "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553"
    assert collector.active_token_ids == market.token_ids
