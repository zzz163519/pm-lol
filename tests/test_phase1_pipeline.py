import json
import sqlite3
from pathlib import Path

from pm_lol.collectors.lolesports_schedule_collector import ScheduleCollector
from pm_lol.collectors.polymarket_market_collector import PolymarketMarketCollector
from pm_lol.collectors.polymarket_quote_recorder import PolymarketQuoteRecorder
from pm_lol.resolvers.market_match_resolver import resolve_pending_markets
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


class FakeMarketClient:
    def search_markets(self, keywords):
        return [
            {
                "selectedMarket": {
                    "id": "t1-gen-game1",
                    "slug": "lol-t1-gen-game1",
                    "question": "LoL: T1 vs Gen.G Esports - Game 1 Winner",
                    "conditionId": "0xt1gen",
                    "active": True,
                    "closed": False,
                    "volume": "100",
                    "liquidity": "50",
                    "outcomes": '["T1", "Gen.G Esports"]',
                    "clobTokenIds": '["yes-token", "no-token"]',
                    "groupItemTitle": "Game 1 Winner",
                    "questionID": "qid",
                }
            }
        ]


class FakeBookClient:
    def get_orderbook(self, token_id):
        return {
            "market": "0xt1gen",
            "asset_id": token_id,
            "timestamp": "1781508217535",
            "bids": [{"price": "0.49", "size": "10"}],
            "asks": [{"price": "0.51", "size": "12"}],
        }


class FakeScheduleClient:
    def get_leagues(self):
        return {"data": {"leagues": [{"slug": "lck", "name": "LCK"}]}}

    def get_schedule(self):
        return {"data": {"schedule": {"events": [{"id": "115548128963037587", "type": "match"}]}}}

    def get_event_details(self, match_id):
        assert match_id == "115548128963037587"
        return json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text())


def test_phase1_collectors_and_resolver_can_run_in_sequence(tmp_path):
    db_path = tmp_path / "phase1.db"
    storage = SQLiteStorage(db_path)

    market_collector = PolymarketMarketCollector(FakeMarketClient(), storage)
    market_collector.run_once()
    PolymarketQuoteRecorder(FakeBookClient(), storage, market_collector.active_token_ids).run_once()
    ScheduleCollector(FakeScheduleClient(), storage).run_once()
    resolver_summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("markets", "quotes", "matches", "games", "resolved_markets")
        }

    assert counts == {
        "markets": 1,
        "quotes": 2,
        "matches": 1,
        "games": 5,
        "resolved_markets": 1,
    }
    assert resolver_summary == {"markets_seen": 1, "resolved": 1, "skipped": 0}
