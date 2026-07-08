import json
import sqlite3
from pathlib import Path

import pytest

from pm_lol.collectors.live_game_state_connector import LiveGameStateConnector
from pm_lol.models import Game, GameStateSnapshot, Match
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"
WINDOW_FIXTURE = FIXTURES / "lolesports-window-t1-gen-g1-15m-sample.json"


def _make_match(match_id: str) -> Match:
    return Match(
        match_id=match_id,
        league="MSI",
        team_a_id="blue-team",
        team_a_name="Blue Team",
        team_b_id="red-team",
        team_b_name="Red Team",
    )


def _make_game(match: Match, game_id: str = "game-cito-1", game_number: int = 1) -> Game:
    return Game(
        game_id=game_id,
        match_id=match.match_id,
        game_number=game_number,
        blue_team_id=match.team_a_id,
        red_team_id=match.team_b_id,
        state="in_game",
    )


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


# ---------------------------------------------------------------------------
# Cito visual-state low-frequency polling
# ---------------------------------------------------------------------------


class FakeCitoVisualClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def get_visual_state(self, game_id):
        assert game_id == "game-cito-1"
        self.calls += 1
        return self.payloads.pop(0)


def _cito_body(*, is_fresh, sample_age, sampled_at, remaining):
    # Mirrors the real Cito visual-state endpoint body shape.
    return {
        "gameId": "game-cito-1",
        "matchId": "match-cito-1",
        "gameTimeSeconds": 1146,
        "gameTime": 1146,
        "blueTeam": {"tag": "BLU", "gold": 34700, "kills": 10, "towers": 0, "dragons": 1, "barons": 0},
        "redTeam": {"tag": "RED", "gold": 36800, "kills": 13, "towers": 3, "dragons": 3, "barons": 0},
        "freshness": {"isFresh": is_fresh, "staleAfterSeconds": 45},
        "sampleAgeSeconds": sample_age,
        "sampledAt": sampled_at,
        "rateLimit": {"remaining": remaining},
        "reliability": "provisional_until_postgame_reconciliation",
    }


def test_cito_poll_writes_freshness_metadata_and_respects_default_budget(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-cito-1")
    game = _make_game(match)
    storage.upsert_match(match)
    storage.upsert_game(game)

    fresh = _cito_body(is_fresh=True, sample_age=18, sampled_at="2026-07-08T09:14:18.516Z", remaining=155)
    stale = _cito_body(is_fresh=False, sample_age=142, sampled_at="2026-07-08T09:14:32.314Z", remaining=154)
    client = FakeCitoVisualClient([fresh, stale])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=2)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT game_clock, source_status, sample_age_seconds, rate_limit_state,
                   error_code, source, paused, winner
            FROM game_state_snapshots
            ORDER BY source_timestamp
            """
        ).fetchall()

    assert summary["polls"] == 2
    assert summary["snapshots_written"] == 2
    assert summary["fresh_snapshots"] == 1
    assert summary["stale_snapshots"] == 1
    assert summary["skipped_snapshots"] == 0
    assert summary["rate_limited"] is False
    assert summary["request_budget_per_min"] == 3
    assert summary["poll_interval_sec"] == 20  # 60 // 3, low-frequency
    assert summary["backoff_seconds"] is None
    assert client.calls == 2

    assert [row["source_status"] for row in rows] == ["fresh", "stale"]
    assert [row["sample_age_seconds"] for row in rows] == [18, 142]
    assert rows[0]["game_clock"] == 1146
    assert json.loads(rows[1]["rate_limit_state"]) == {"remaining": 154}
    assert rows[0]["error_code"] is None
    assert rows[0]["source"] == "cito_visual_state"
    # paused unobserved -> stored as unknown (NULL), never a hardcoded 0.
    assert rows[0]["paused"] is None
    assert rows[0]["winner"] is None


def test_cito_poll_skips_not_ready_without_fabricating(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-cito-1")
    game = _make_game(match)
    storage.upsert_match(match)
    storage.upsert_game(game)

    not_ready = {
        "success": True,
        "status": "not_ready",
        "gameId": game.game_id,
        "retryAfterSeconds": 10,
        "message": "No accepted visual live state is available for this game yet",
    }
    client = FakeCitoVisualClient([not_ready, not_ready])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=2)

    with sqlite3.connect(db_path) as conn:
        state_rows = conn.execute("SELECT COUNT(*) FROM game_state_snapshots").fetchone()[0]

    assert summary["snapshots_written"] == 0
    assert summary["skipped_snapshots"] == 2
    assert state_rows == 0


def test_cito_poll_backs_off_on_429_without_fake_snapshot(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-cito-429")
    game = _make_game(match)
    storage.upsert_match(match)
    storage.upsert_game(game)
    client = FakeCitoVisualClient([{"statusCode": 429, "body": {"error": "rate_limited"}}])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=3)

    with sqlite3.connect(db_path) as conn:
        state_rows = conn.execute("SELECT COUNT(*) FROM game_state_snapshots").fetchone()[0]

    assert summary["polls"] == 1  # stopped immediately, did not burn the budget
    assert summary["snapshots_written"] == 0
    assert summary["rate_limited"] is True
    assert summary["backoff_seconds"] >= 60
    assert summary["backoff_until"] is not None
    assert state_rows == 0


def test_cito_poll_default_budget_stays_under_free_plan_ceiling():
    match = _make_match("match-cito-1")
    game = _make_game(match)
    connector = LiveGameStateConnector(FakeCitoVisualClient([]), storage=None)

    # Default budget is well under the 10 req/min free-plan ceiling.
    summary = connector.run_cito_visual_poll(game, max_polls=0)
    assert summary["request_budget_per_min"] <= 8
    assert 60 / summary["request_budget_per_min"] >= 15  # >=15s spacing between polls

    # Budgets above the free-plan ceiling are rejected outright.
    with pytest.raises(ValueError):
        connector.run_cito_visual_poll(game, max_polls=1, request_budget_per_min=11)


# ---------------------------------------------------------------------------
# paused tri-state storage + legacy migration
# ---------------------------------------------------------------------------


def _base_snapshot(**overrides) -> GameStateSnapshot:
    fields = dict(
        game_id="game-cito-1",
        timestamp="2026-07-08T09:14:18.516Z",
        game_state="in_game",
        blue_gold=100,
        red_gold=90,
        blue_towers=0,
        red_towers=0,
        blue_dragons=[],
        red_dragons=[],
        blue_barons=0,
        red_barons=0,
        blue_kills=1,
        red_kills=0,
    )
    fields.update(overrides)
    return GameStateSnapshot(**fields)


def test_paused_unknown_is_stored_as_null_and_true_false_roundtrip(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-cito-1")
    game = _make_game(match)
    storage.upsert_match(match)
    storage.upsert_game(game)

    storage.insert_game_state_snapshot(_base_snapshot(timestamp="t-unknown", paused=None))
    storage.insert_game_state_snapshot(_base_snapshot(timestamp="t-true", paused=True))
    storage.insert_game_state_snapshot(_base_snapshot(timestamp="t-false", paused=False))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = {
            row["source_timestamp"]: row["paused"]
            for row in conn.execute("SELECT source_timestamp, paused FROM game_state_snapshots")
        }

    assert rows["t-unknown"] is None  # unknown, not a hardcoded 0
    assert rows["t-true"] == 1
    assert rows["t-false"] == 0


LEGACY_GAME_STATE_DDL = """
CREATE TABLE games (
    game_id TEXT PRIMARY KEY, match_id TEXT, game_number INTEGER,
    blue_team_id TEXT, red_team_id TEXT, state TEXT, start_time TEXT, patch TEXT,
    raw_json TEXT, source TEXT, confidence REAL, created_at TEXT, updated_at TEXT
);
CREATE TABLE game_state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    game_clock REAL,
    observed_at TEXT NOT NULL,
    source_timestamp TEXT NOT NULL,
    source_latency_sec REAL,
    game_state TEXT NOT NULL,
    blue_gold INTEGER NOT NULL, red_gold INTEGER NOT NULL, gold_diff INTEGER NOT NULL,
    blue_towers INTEGER NOT NULL, red_towers INTEGER NOT NULL,
    blue_dragons INTEGER NOT NULL, red_dragons INTEGER NOT NULL,
    blue_dragons_json TEXT NOT NULL, red_dragons_json TEXT NOT NULL,
    first_dragon_team TEXT,
    blue_barons INTEGER NOT NULL, red_barons INTEGER NOT NULL,
    baron_status TEXT, elder_status TEXT,
    blue_kills INTEGER NOT NULL, red_kills INTEGER NOT NULL,
    blue_inhibitors INTEGER, red_inhibitors INTEGER,
    paused INTEGER NOT NULL,
    finished INTEGER NOT NULL,
    winner TEXT,
    participants_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(game_id, source_timestamp)
);
"""


def test_legacy_paused_not_null_is_migrated_to_nullable(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(LEGACY_GAME_STATE_DDL)
    conn.execute("INSERT INTO games (game_id, match_id, state) VALUES ('g1', 'm1', 'in_game')")
    conn.execute(
        """
        INSERT INTO game_state_snapshots (
            snapshot_id, game_id, observed_at, source_timestamp, game_state,
            blue_gold, red_gold, gold_diff, blue_towers, red_towers,
            blue_dragons, red_dragons, blue_dragons_json, red_dragons_json,
            blue_barons, red_barons, blue_kills, red_kills, paused, finished,
            participants_json, raw_json, source, confidence, created_at
        )
        VALUES ('g1:legacy', 'g1', 't', 'ts-legacy', 'in_game',
                1, 2, -1, 0, 0, 0, 0, '[]', '[]', 0, 0, 0, 0, 0, 0,
                '{}', '{}', 'legacy_src', 1.0, 't')
        """
    )
    conn.commit()
    conn.close()

    # Opening the DB runs the migration.
    SQLiteStorage(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        notnull = {row["name"]: row["notnull"] for row in conn.execute("PRAGMA table_info(game_state_snapshots)")}
        legacy = conn.execute("SELECT paused, source FROM game_state_snapshots WHERE snapshot_id='g1:legacy'").fetchone()
        # NULL paused now allowed on the migrated table.
        conn.execute(
            "INSERT INTO game_state_snapshots (snapshot_id, game_id, observed_at, source_timestamp, "
            "game_state, blue_gold, red_gold, gold_diff, blue_towers, red_towers, blue_dragons, "
            "red_dragons, blue_dragons_json, red_dragons_json, blue_barons, red_barons, blue_kills, "
            "red_kills, paused, finished, participants_json, raw_json, source_status, rate_limit_state, "
            "source, confidence, created_at) VALUES ('g1:new','g1','t','ts-new','in_game',1,2,-1,0,0,0,0,"
            "'[]','[]',0,0,0,0,NULL,0,'{}','{}','ok','{}','cito',1.0,'t')"
        )
        conn.commit()
        migrated_null = conn.execute("SELECT paused FROM game_state_snapshots WHERE snapshot_id='g1:new'").fetchone()[0]

    assert notnull["paused"] == 0  # NOT NULL constraint relaxed
    assert legacy["paused"] == 0  # legacy row preserved
    assert legacy["source"] == "legacy_src"
    assert migrated_null is None


# ---------------------------------------------------------------------------
# LoLEsports postgame reconciliation + per-game winner (no series fallback)
# ---------------------------------------------------------------------------


def _window_payload_for(game_id: str, match_id: str) -> dict:
    payload = json.loads(WINDOW_FIXTURE.read_text())
    payload["esportsGameId"] = game_id
    payload["esportsMatchId"] = match_id
    payload["sampleFrame"]["gameState"] = "completed"
    return payload


class FakeReconciliationClient:
    """event details + window client for a single reconcilable game."""

    def __init__(self, event, expected_game_id, match_id):
        self._event = event
        self._expected_game_id = expected_game_id
        self._match_id = match_id

    def get_event_details(self, match_id):
        assert match_id == self._match_id
        return {"data": {"event": self._event}}

    def get_window(self, game_id):
        assert game_id == self._expected_game_id
        return _window_payload_for(game_id, self._match_id)


def _game_teams(blue_outcome=None, red_outcome=None):
    blue = {"id": "blue-team", "side": "blue"}
    red = {"id": "red-team", "side": "red"}
    if blue_outcome is not None:
        blue["result"] = {"outcome": blue_outcome}
    if red_outcome is not None:
        red["result"] = {"outcome": red_outcome}
    return [blue, red]


def _bo5_event(match_id, games):
    return {
        "id": match_id,
        "state": "completed",
        "match": {
            # Series score: blue leads 3-2. This must NEVER be used to infer a
            # single game's winner.
            "teams": [
                {"id": "blue-team", "name": "Blue Team", "result": {"gameWins": 3}},
                {"id": "red-team", "name": "Red Team", "result": {"gameWins": 2}},
            ],
            "games": games,
        },
    }


def test_reconciliation_writes_final_picks_and_per_game_winner(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-final")
    game = _make_game(match, game_id="game-final-1", game_number=1)
    storage.upsert_match(match)
    storage.upsert_game(game)

    event = {
        "id": "match-final",
        "state": "completed",
        "match": {
            "teams": [
                {"id": "blue-team", "name": "Blue Team", "result": {"gameWins": 0}},
                {"id": "red-team", "name": "Red Team", "result": {"gameWins": 1}},
            ],
            "games": [
                {
                    "id": "game-final-1",
                    "number": 1,
                    "state": "completed",
                    "teams": _game_teams(blue_outcome="loss", red_outcome="win"),
                }
            ],
        },
    }
    client = FakeReconciliationClient(event, "game-final-1", "match-final")

    summary = LiveGameStateConnector(client, storage).reconcile_lolesports_game(game)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        game_row = conn.execute("SELECT state FROM games WHERE game_id = ?", (game.game_id,)).fetchone()
        snap = conn.execute(
            "SELECT winner, source_status, source, error_code FROM game_state_snapshots WHERE game_id = ?",
            (game.game_id,),
        ).fetchone()
        draft_rows = conn.execute("SELECT COUNT(*) FROM draft_snapshots WHERE game_id = ?", (game.game_id,)).fetchone()[0]

    assert summary["winner"] == "red-team"
    assert summary["winner_known"] is True
    assert summary["error_code"] is None
    assert summary["draft_snapshots"] == 10
    assert summary["game_state"] == "completed"
    assert game_row["state"] == "completed"
    assert snap["winner"] == "red-team"
    assert snap["source_status"] == "final"
    assert snap["error_code"] is None
    assert draft_rows == 10


def test_reconciliation_uses_per_game_outcome_not_series_score(tmp_path):
    """BO5 3-2: game 3 is won by the series LOSER (red). The per-game outcome must
    win, so the series leader (blue) must not be attributed the game."""
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-bo5")
    game3 = _make_game(match, game_id="game-bo5-3", game_number=3)
    storage.upsert_match(match)
    storage.upsert_game(game3)

    games = [
        {"id": "game-bo5-3", "number": 3, "state": "completed", "teams": _game_teams("win", "loss")},
    ]
    # Flip game 3 so the SERIES LOSER (red) actually won this specific game.
    games[0]["teams"] = _game_teams(blue_outcome="loss", red_outcome="win")
    event = _bo5_event("match-bo5", games)
    client = FakeReconciliationClient(event, "game-bo5-3", "match-bo5")

    summary = LiveGameStateConnector(client, storage).reconcile_lolesports_game(game3)

    with sqlite3.connect(db_path) as conn:
        winner = conn.execute(
            "SELECT winner FROM game_state_snapshots WHERE game_id = 'game-bo5-3'"
        ).fetchone()[0]

    # Series leader is blue (3-2), but red won this game.
    assert summary["winner"] == "red-team"
    assert winner == "red-team"


def test_reconciliation_writes_winner_unknown_when_no_per_game_outcome(tmp_path):
    """BO5 game with no per-game outcome must store NULL winner + winner_unknown,
    never the series leader inferred from gameWins."""
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    match = _make_match("match-bo5")
    game5 = _make_game(match, game_id="game-bo5-5", game_number=5)
    storage.upsert_match(match)
    storage.upsert_game(game5)

    # No `result.outcome` on either team => per-game winner is unknown.
    games = [
        {"id": "game-bo5-5", "number": 5, "state": "completed", "teams": _game_teams()},
    ]
    event = _bo5_event("match-bo5", games)
    client = FakeReconciliationClient(event, "game-bo5-5", "match-bo5")

    summary = LiveGameStateConnector(client, storage).reconcile_lolesports_game(game5)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        snap = conn.execute(
            "SELECT winner, error_code, source_status FROM game_state_snapshots WHERE game_id = 'game-bo5-5'"
        ).fetchone()

    assert summary["winner"] is None
    assert summary["winner_known"] is False
    assert summary["error_code"] == "winner_unknown"
    assert snap["winner"] is None  # not "blue-team" (the 3-2 series leader)
    assert snap["error_code"] == "winner_unknown"
    assert snap["source_status"] == "final"
