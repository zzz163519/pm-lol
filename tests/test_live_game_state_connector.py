import json
import sqlite3
from pathlib import Path

from pm_lol.collectors.live_game_state_connector import LiveGameStateConnector
from pm_lol.models import Game, Match
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


class FakeLiveClient:
    def __init__(self):
        in_game = json.loads((FIXTURES / "lolesports-window-t1-gen-g1-15m-sample.json").read_text())
        finished = json.loads(json.dumps(in_game))
        finished["sampleFrame"]["gameState"] = "finished"
        self.payloads = [
            {"esportsGameId": in_game["esportsGameId"], "sampleFrame": {"gameState": "scheduled"}},
            in_game,
            finished,
        ]

    def get_window(self, game_id):
        assert game_id == "115548128963037588"
        return self.payloads.pop(0)


def test_live_connector_simulates_full_game_lifecycle(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = Match(
        match_id="115548128963037587",
        league="LCK",
        team_a_id="98767991853197861",
        team_a_name="T1",
        team_b_id="100205573495116443",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="115548128963037588",
        match_id=match.match_id,
        game_number=1,
        blue_team_id=match.team_a_id,
        red_team_id=match.team_b_id,
        state="scheduled",
    )
    storage.upsert_match(match)
    storage.upsert_game(game)

    summary = LiveGameStateConnector(FakeLiveClient(), storage).run_game_lifecycle(game)

    with sqlite3.connect(db_path) as conn:
        game_state = conn.execute("SELECT state FROM games WHERE game_id = ?", (game.game_id,)).fetchone()[0]
        state_rows = conn.execute("SELECT COUNT(*) FROM game_state_snapshots").fetchone()[0]
        draft_rows = conn.execute("SELECT COUNT(*) FROM draft_snapshots").fetchone()[0]

    assert summary == {
        "polls": 3,
        "state_transitions": ["scheduled", "in_game", "finished"],
        "game_state_snapshots": 1,
        "draft_snapshots": 10,
        "stopped": True,
    }
    assert game_state == "finished"
    assert state_rows == 1
    assert draft_rows == 10
