import json
import sqlite3
from pathlib import Path

import pytest

from pm_lol.collectors.live_game_state_connector import (
    CitoApiClient,
    CitoBudgetScheduler,
    LiveGameStateConnector,
)
from pm_lol.models import Game, Match
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"
WINDOW_FIXTURE = FIXTURES / "lolesports-window-t1-gen-g1-15m-sample.json"


def _make_match_and_game(
    storage: SQLiteStorage,
    *,
    match_id: str,
    game_id: str,
    blue_team_id: str = "blue-team",
    red_team_id: str = "red-team",
    game_number: int = 1,
    state: str = "in_game",
) -> Game:
    match = Match(
        match_id=match_id,
        league="MSI",
        team_a_id=blue_team_id,
        team_a_name="Blue Team",
        team_b_id=red_team_id,
        team_b_name="Red Team",
    )
    game = Game(
        game_id=game_id,
        match_id=match_id,
        game_number=game_number,
        blue_team_id=blue_team_id,
        red_team_id=red_team_id,
        state=state,
    )
    storage.upsert_match(match)
    storage.upsert_game(game)
    return game


class FakeLiveClient:
    def __init__(self):
        in_game = json.loads(WINDOW_FIXTURE.read_text())
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


class FakeCitoVisualClient:
    def __init__(self, payloads, expected_game_id="game-cito-1"):
        self.payloads = list(payloads)
        self.expected_game_id = expected_game_id
        self.calls = 0

    def get_visual_state(self, game_id):
        assert game_id == self.expected_game_id
        self.calls += 1
        return self.payloads.pop(0)


def _cito_fresh(game_id, match_id):
    return {
        "success": True,
        "source": "visual_live_extraction",
        "status": "fresh",
        "sampleAgeSeconds": 18,
        "sampledAt": "2026-07-08T09:14:18.516Z",
        "gameId": game_id,
        "matchId": match_id,
        "gameTimeSeconds": 1146,
        "blueTeam": {"tag": "BLU", "gold": 34700, "kills": 10, "towers": 0, "dragons": 1, "barons": 0},
        "redTeam": {"tag": "RED", "gold": 36800, "kills": 13, "towers": 3, "dragons": 3, "barons": 0},
        "freshness": {"isFresh": True, "staleAfterSeconds": 45},
        "rateLimit": {"remaining": 155},
    }


def test_cito_poll_writes_freshness_metadata_and_respects_default_budget(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-cito-1", game_id="game-cito-1")

    fresh = _cito_fresh(game.game_id, "match-cito-1")
    stale = {
        **fresh,
        "status": "stale",
        "sampleAgeSeconds": 142,
        "sampledAt": "2026-07-08T09:14:32.314Z",
        "freshness": {"isFresh": False, "staleAfterSeconds": 45},
        "rateLimit": {"remaining": 154},
    }
    client = FakeCitoVisualClient([fresh, stale])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=2)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT game_clock, source_status, sample_age_seconds, rate_limit_state,
                   error_code, source
            FROM game_state_snapshots
            ORDER BY source_timestamp
            """
        ).fetchall()

    assert summary == {
        "polls": 2,
        "snapshots_written": 2,
        "fresh_snapshots": 1,
        "stale_snapshots": 1,
        "partial_snapshots": 0,
        "unavailable_numeric_snapshots": 1,
        "skipped_snapshots": 0,
        "rate_limited": False,
        "request_budget_per_min": 6,
        "min_interval_sec": 10,
        "backoff_seconds": None,
        "backoff_until": None,
    }
    assert client.calls == 2
    assert [row["source_status"] for row in rows] == ["fresh", "stale"]
    assert [row["sample_age_seconds"] for row in rows] == [18, 142]
    assert rows[0]["game_clock"] == 1146
    assert json.loads(rows[1]["rate_limit_state"]) == {"remaining": 154}
    assert rows[0]["error_code"] is None
    assert rows[0]["source"] == "cito_visual_state"


def test_cito_poll_backs_off_on_429_without_fake_snapshot(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-cito-429", game_id="game-cito-1")
    client = FakeCitoVisualClient([{"statusCode": 429, "body": {"error": "rate_limited"}}])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=3)

    with sqlite3.connect(db_path) as conn:
        state_rows = conn.execute("SELECT COUNT(*) FROM game_state_snapshots").fetchone()[0]

    # 429 must stop the loop and record a >=60s backoff, never fabricate a snapshot.
    assert summary["polls"] == 1
    assert summary["snapshots_written"] == 0
    assert summary["rate_limited"] is True
    assert summary["backoff_seconds"] >= 60
    assert summary["backoff_until"] is not None
    assert state_rows == 0


def test_cito_poll_rejects_budget_at_or_above_free_plan_and_paces_under_10_per_min(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-budget", game_id="game-cito-1")

    # Budgets at or above the 10 req/min free-plan ceiling are rejected outright.
    for bad_budget in (10, 12, 60):
        with pytest.raises(ValueError):
            LiveGameStateConnector(
                FakeCitoVisualClient([]), storage
            ).run_cito_visual_poll(game, max_polls=1, request_budget_per_min=bad_budget)

    sleeps: list[int] = []
    fresh = _cito_fresh(game.game_id, "match-budget")
    later = {**fresh, "sampledAt": "2026-07-08T09:20:00.000Z"}
    connector = LiveGameStateConnector(
        FakeCitoVisualClient([fresh, later]),
        storage,
        poll_interval_sec=1,
        sleep_func=sleeps.append,
    )

    summary = connector.run_cito_visual_poll(game, max_polls=2)

    # Default global budget stays in the CAL-70 6-8 req/min range and below the free-plan ceiling.
    assert summary["request_budget_per_min"] == 6
    assert summary["request_budget_per_min"] < 10
    # Pacing enforces >= 60/budget seconds between calls -> effective rate < 10 req/min.
    assert summary["min_interval_sec"] == 10
    assert sleeps and all(gap >= 60 / summary["request_budget_per_min"] for gap in sleeps)
    assert 60 / summary["min_interval_sec"] < 10


def test_cito_budget_scheduler_keeps_multi_match_plan_under_free_plan():
    scheduler = CitoBudgetScheduler(request_budget_per_min=6, poll_interval_sec=1)

    plan = scheduler.plan_offsets(targets=["game-a", "game-b", "game-c"], polls_per_target=3)

    assert scheduler.min_interval_sec == 10
    assert len(plan) == 9
    assert plan[:3] == [
        {"offset_sec": 0, "target": "game-a"},
        {"offset_sec": 10, "target": "game-b"},
        {"offset_sec": 20, "target": "game-c"},
    ]
    first_minute_requests = [item for item in plan if item["offset_sec"] < 60]
    assert len(first_minute_requests) == 6
    assert len(first_minute_requests) < 10


def test_cito_poll_persists_paused_unknown_and_known(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-paused", game_id="game-cito-1")

    # No paused flag and no pause-like gameState -> unknown (must persist as NULL).
    unknown = _cito_fresh(game.game_id, "match-paused")
    unknown["sampledAt"] = "2026-07-08T09:10:00.000Z"
    # Explicit paused gameState -> known True (proves we do not hardcode False).
    paused = {**unknown, "sampledAt": "2026-07-08T09:12:00.000Z", "gameState": "paused"}
    client = FakeCitoVisualClient([unknown, paused])

    LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=2)

    # Raw column stays NULL for unknown rather than a fabricated 0/false.
    with sqlite3.connect(db_path) as conn:
        raw_paused = [
            row[0]
            for row in conn.execute(
                "SELECT paused FROM game_state_snapshots ORDER BY source_timestamp"
            ).fetchall()
        ]
    assert raw_paused == [None, 1]

    # Typed read-back round-trips the tri-state (None / True), never coercing to False.
    snapshots = storage.get_game_state_snapshots(game.game_id)
    assert [snap.paused for snap in snapshots] == [None, True]


def test_cito_poll_persists_on_break_zero_confidence_as_unavailable_numeric_state(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-break", game_id="game-cito-1")

    on_break = {
        "status": "on_break",
        "reason": "broadcast_desk_or_break_detected",
        "sampleAgeSeconds": 17,
        "gameId": game.game_id,
        "matchId": "match-break",
        "gameTimeSeconds": 0,
        "confidence": {
            "gold": 0,
            "kills": 0,
            "objectives": 0,
            "timer": 0,
        },
        "dataQuality": {"numericLiveStats": "unavailable"},
        "blueTeam": {"gold": 0, "kills": 0, "towers": 0, "dragons": 0, "barons": 0},
        "redTeam": {"gold": 0, "kills": 0, "towers": 0, "dragons": 0, "barons": 0},
    }
    client = FakeCitoVisualClient([on_break])

    summary = LiveGameStateConnector(client, storage).run_cito_visual_poll(game, max_polls=1)

    assert summary["snapshots_written"] == 1
    assert summary["unavailable_numeric_snapshots"] == 1
    snapshot = storage.get_game_state_snapshots(game.game_id)[0]
    assert snapshot.source_status == "on_break"
    assert snapshot.error_code == "live_numeric_stats_unavailable"
    assert snapshot.raw["reason"] == "broadcast_desk_or_break_detected"
    assert snapshot.raw["confidence"] == {
        "gold": 0,
        "kills": 0,
        "objectives": 0,
        "timer": 0,
    }
    assert snapshot.raw["dataQuality"] == {"numericLiveStats": "unavailable"}


def test_cito_api_client_reads_env_key_and_calls_required_lol_endpoints(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        content = b"{}"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls.append({"url": url, "headers": headers, "timeout": timeout})
            return FakeResponse({"url": url})

    monkeypatch.setenv("CITO_API_KEY", "env-secret")
    client = CitoApiClient(session=FakeSession(), timeout=7)

    assert client.list_live_matches()["url"].endswith("/lol/live")
    assert client.list_today_schedule()["url"].endswith("/lol/schedule/today")
    assert client.get_match_coverage("match-1")["url"].endswith("/lol/matches/match-1/coverage")
    assert client.get_visual_state("game-1")["url"].endswith("/lol/live/game-1/visual-state")
    assert all(call["headers"] == {"x-api-key": "env-secret"} for call in calls)
    assert all(call["timeout"] == 7 for call in calls)


class FakeEventDetailsClient:
    def __init__(self, event, expected_match_id, expected_game_id, game_state="completed"):
        self._event = event
        self.expected_match_id = expected_match_id
        self.expected_game_id = expected_game_id
        self.game_state = game_state

    def get_event_details(self, match_id):
        assert match_id == self.expected_match_id
        return {"event": self._event}

    def get_window(self, game_id):
        assert game_id == self.expected_game_id
        payload = json.loads(WINDOW_FIXTURE.read_text())
        payload["esportsGameId"] = game_id
        payload["esportsMatchId"] = self.expected_match_id
        payload["sampleFrame"]["gameState"] = self.game_state
        return payload


def test_lolesports_reconciliation_writes_picks_and_winner(tmp_path):
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(storage, match_id="match-final", game_id="game-final-1")

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
                    "teams": [
                        {"id": "blue-team", "side": "blue", "result": {"outcome": "loss"}},
                        {"id": "red-team", "side": "red", "result": {"outcome": "win"}},
                    ],
                }
            ],
        },
    }
    client = FakeEventDetailsClient(event, "match-final", "game-final-1")
    summary = LiveGameStateConnector(client, storage).reconcile_lolesports_game(game)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        game_row = conn.execute("SELECT state FROM games WHERE game_id = ?", (game.game_id,)).fetchone()
        snapshot_row = conn.execute(
            "SELECT winner, source_status, source, error_code FROM game_state_snapshots WHERE game_id = ?",
            (game.game_id,),
        ).fetchone()
        draft_rows = conn.execute(
            "SELECT COUNT(*) FROM draft_snapshots WHERE game_id = ?", (game.game_id,)
        ).fetchone()[0]

    assert summary == {
        "match_id": "match-final",
        "game_id": "game-final-1",
        "draft_snapshots": 10,
        "winner": "red-team",
        "winner_error_code": None,
        "game_state": "completed",
    }
    assert game_row["state"] == "completed"
    assert snapshot_row["winner"] == "red-team"
    assert snapshot_row["source_status"] == "final"
    assert snapshot_row["source"] == "lolesports_livestats_window"
    assert snapshot_row["error_code"] is None
    assert draft_rows == 10


def test_reconciliation_does_not_infer_game_winner_from_series_score(tmp_path):
    """BO5 3-2: a game won by the series *loser* must not be back-filled from gameWins.

    When per-game outcome is absent, winner stays unknown (NULL) with a
    ``winner_unknown`` error code instead of the 3-1 series leader.
    """
    db_path = tmp_path / "live.db"
    storage = SQLiteStorage(db_path)
    game = _make_match_and_game(
        storage,
        match_id="bo5-match",
        game_id="bo5-g2",
        blue_team_id="series-winner",
        red_team_id="series-loser",
        game_number=2,
    )

    event = {
        "id": "bo5-match",
        "state": "completed",
        "match": {
            # Series decided 3-2 in favour of "series-winner"...
            "teams": [
                {"id": "series-winner", "name": "Series Winner", "result": {"gameWins": 3}},
                {"id": "series-loser", "name": "Series Loser", "result": {"gameWins": 2}},
            ],
            "games": [
                {
                    "id": "bo5-g2",
                    "number": 2,
                    "state": "completed",
                    # ...but this individual game has NO per-game outcome recorded.
                    "teams": [
                        {"id": "series-winner", "side": "blue"},
                        {"id": "series-loser", "side": "red"},
                    ],
                }
            ],
        },
    }
    client = FakeEventDetailsClient(event, "bo5-match", "bo5-g2")
    summary = LiveGameStateConnector(client, storage).reconcile_lolesports_game(game)

    assert summary["winner"] is None
    assert summary["winner_error_code"] == "winner_unknown"
    # Never fabricate the series leader as the game winner.
    assert summary["winner"] != "series-winner"

    snapshots = storage.get_game_state_snapshots(game.game_id)
    assert len(snapshots) == 1
    assert snapshots[0].winner is None
    assert snapshots[0].error_code == "winner_unknown"

    with sqlite3.connect(db_path) as conn:
        raw_winner = conn.execute(
            "SELECT winner FROM game_state_snapshots WHERE game_id = ?", (game.game_id,)
        ).fetchone()[0]
    assert raw_winner is None
