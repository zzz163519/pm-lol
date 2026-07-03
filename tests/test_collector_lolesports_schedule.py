import json
import sqlite3
from pathlib import Path

from pm_lol.collectors.lolesports_schedule_collector import ScheduleCollector
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


class FakeScheduleClient:
    def get_leagues(self):
        return {"data": {"leagues": [{"slug": "lck", "name": "LCK"}]}}

    def get_schedule(self):
        return {"events": [{"match_id": "115548128963037587"}]}

    def get_event_details(self, match_id):
        assert match_id == "115548128963037587"
        return json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text())


def test_schedule_collector_writes_match_and_games(tmp_path):
    db_path = tmp_path / "schedule.db"
    storage = SQLiteStorage(db_path)
    collector = ScheduleCollector(FakeScheduleClient(), storage)

    summary = collector.run_once()

    with sqlite3.connect(db_path) as conn:
        match_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        first_game = conn.execute(
            "SELECT game_number, blue_team_id, red_team_id FROM games ORDER BY game_number LIMIT 1"
        ).fetchone()

    assert summary == {"leagues_seen": 1, "events_seen": 1, "matches_written": 1, "games_written": 5}
    assert match_count == 1
    assert game_count == 5
    assert first_game == ("1", "98767991853197861", "100205573495116443") or first_game == (
        1,
        "98767991853197861",
        "100205573495116443",
    )
