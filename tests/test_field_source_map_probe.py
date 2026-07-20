import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "field_source_map_probe.py"
FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


@pytest.fixture(autouse=True)
def lolesports_api_key(monkeypatch):
    monkeypatch.setenv("LOLESPORTS_API_KEY", "test-only-lolesports-key")


def load_probe_module():
    spec = importlib.util.spec_from_file_location("field_source_map_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconcile_winner_from_completed_event_details_fixture():
    probe = load_probe_module()
    payload = json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text())

    winner = probe.reconcile_winner(payload)

    assert winner["status"] == "present"
    assert winner["sample"]["code"] == "T1"
    assert winner["sample"]["gameWins"] == 3
    assert winner["completedGameCount"] >= 1


def test_dual_source_probe_routes_fields_to_expected_sources(tmp_path):
    probe = load_probe_module()

    def fake_get(url, headers=None, timeout=20.0):
        if url.endswith("/lol/live"):
            return {
                "data": [{"matchId": "lol-match-1", "team1": {"code": "G2"}, "team2": {"code": "T1"}}]
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:00Z"}
        if url.endswith("/lol/matches/1/coverage"):
            return {"active_live_game_id": "lol-game-2"}, {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:01Z",
            }
        if url.endswith("/lol/live/2/visual-state"):
            return {
                "status": "provisional",
                "gameTimeFormatted": "31:01",
                "gameTimeSeconds": 1861,
                "blueTeam": {"tag": "G2", "gold": 1000, "kills": 1, "dragons": 1, "barons": 0, "towers": 2},
                "redTeam": {"tag": "T1", "gold": 900, "kills": 0, "dragons": 0, "barons": 0, "towers": 1},
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:02Z"}
        if "getEventDetails" in url:
            return json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text()), {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:03Z",
            }
        if url.endswith("/livestats/v1/window/2"):
            return {
                "gameMetadata": {
                    "blueTeamMetadata": {
                        "participantMetadata": [{"championId": str(index)} for index in range(5)]
                    },
                    "redTeamMetadata": {
                        "participantMetadata": [{"championId": str(index)} for index in range(5, 10)]
                    },
                }
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:04Z"}
        raise AssertionError(url)

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        timeout_sec=20,
        http_get=fake_get,
        now=lambda: "2026-07-08T08:00:05Z",
    )

    assert result["target"] == {"teams": ["T1", "G2"], "matchId": "1", "gameId": "2"}
    assert result["fieldCoverage"]["draftPicks"]["source"] == "lolesports_livestats"
    assert result["fieldCoverage"]["gold"]["source"] == "cito_visual_state"
    assert result["fieldCoverage"]["winner"]["source"] == "lolesports_event_details"
    assert result["fieldCoverage"]["winner"]["status"] == "present"


def test_probe_falls_back_to_schedule_when_live_is_rate_limited(tmp_path):
    probe = load_probe_module()
    seen_urls = []

    def fake_get(url, headers=None, timeout=20.0):
        seen_urls.append(url)
        if url.endswith("/lol/live"):
            return None, {
                "ok": False,
                "statusCode": 429,
                "errorClass": "rate_limited",
                "url": url,
                "observedAt": "2026-07-08T08:00:00Z",
            }
        if url.endswith("/lol/schedule/today"):
            return {
                "matches": [{"id": "lol-match-10", "team1": {"shortName": "T1"}, "team2": {"shortName": "G2"}}]
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:01Z"}
        if url.endswith("/lol/matches/10/coverage"):
            return {"active_live_game_id": "lol-game-20"}, {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:02Z",
            }
        if url.endswith("/lol/live/20/visual-state"):
            return {
                "status": "provisional",
                "gameTimeFormatted": "10:00",
                "blueTeam": {"tag": "T1", "gold": 10000, "kills": 3, "dragons": 1, "barons": 0, "towers": 1},
                "redTeam": {"tag": "G2", "gold": 9000, "kills": 1, "dragons": 0, "barons": 0, "towers": 0},
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:03Z"}
        if "getEventDetails" in url:
            return {"data": {"event": {"match": {"teams": [], "games": []}}}}, {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:04Z",
            }
        if url.endswith("/livestats/v1/window/20"):
            return {}, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:05Z"}
        raise AssertionError(url)

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        timeout_sec=20,
        http_get=fake_get,
        now=lambda: "2026-07-08T08:00:06Z",
    )

    assert any(url.endswith("/lol/schedule/today") for url in seen_urls)
    assert result["target"]["matchId"] == "10"
    assert result["target"]["gameId"] == "20"
    assert result["requests"]["citoScheduleToday"]["statusCode"] == 200


def test_probe_uses_explicit_match_and_game_ids_without_discovery(tmp_path):
    probe = load_probe_module()
    seen_urls = []

    def fake_get(url, headers=None, timeout=20.0):
        seen_urls.append(url)
        if url.endswith("/lol/live/20/visual-state"):
            return {
                "status": "completed",
                "gameTimeSeconds": 1800,
                "blueTeam": {"tag": "T1", "gold": 50000, "kills": 10, "dragons": 2, "barons": 1, "towers": 8},
                "redTeam": {"tag": "G2", "gold": 45000, "kills": 5, "dragons": 1, "barons": 0, "towers": 3},
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:00Z"}
        if "getEventDetails" in url:
            return json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text()), {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:01Z",
            }
        if url.endswith("/livestats/v1/window/20"):
            return {
                "gameMetadata": {
                    "blueTeamMetadata": {"participantMetadata": [{"championId": str(index)} for index in range(5)]},
                    "redTeamMetadata": {"participantMetadata": [{"championId": str(index)} for index in range(5, 10)]},
                }
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:02Z"}
        raise AssertionError(url)

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        timeout_sec=20,
        http_get=fake_get,
        now=lambda: "2026-07-08T08:00:03Z",
        match_id="10",
        game_id="20",
    )

    assert result["target"] == {"teams": ["T1", "G2"], "matchId": "10", "gameId": "20"}
    assert not any(url.endswith("/lol/live") for url in seen_urls)
    assert not any(url.endswith("/lol/schedule/today") for url in seen_urls)
    assert not any(url.endswith("/lol/matches/10/coverage") for url in seen_urls)
    assert result["requests"]["citoLive"]["errorClass"] == "skipped_explicit_match_id"


def test_probe_polls_event_details_until_winner_is_available(tmp_path):
    probe = load_probe_module()
    event_detail_calls = 0

    def fake_get(url, headers=None, timeout=20.0):
        nonlocal event_detail_calls
        if url.endswith("/lol/live/20/visual-state"):
            return {
                "status": "completed",
                "gameTimeSeconds": 1800,
                "blueTeam": {"tag": "T1", "gold": 50000, "kills": 10, "dragons": 2, "barons": 1, "towers": 8},
                "redTeam": {"tag": "G2", "gold": 45000, "kills": 5, "dragons": 1, "barons": 0, "towers": 3},
            }, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:00Z"}
        if "getEventDetails" in url:
            event_detail_calls += 1
            if event_detail_calls == 1:
                return {"data": {"event": {"match": {"teams": [], "games": []}}}}, {
                    "ok": True,
                    "statusCode": 200,
                    "url": url,
                    "observedAt": "2026-07-08T08:00:01Z",
                }
            return json.loads((FIXTURES / "lolesports-event-t1-gen-sample.json").read_text()), {
                "ok": True,
                "statusCode": 200,
                "url": url,
                "observedAt": "2026-07-08T08:00:02Z",
            }
        if url.endswith("/livestats/v1/window/20"):
            return {}, {"ok": True, "statusCode": 200, "url": url, "observedAt": "2026-07-08T08:00:03Z"}
        raise AssertionError(url)

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        timeout_sec=20,
        http_get=fake_get,
        now=lambda: "2026-07-08T08:00:04Z",
        match_id="10",
        game_id="20",
        winner_poll_attempts=2,
        winner_poll_interval_sec=0,
    )

    assert event_detail_calls == 2
    assert result["fieldCoverage"]["winner"]["status"] == "present"
    assert result["requests"]["lolesportsEventDetailsPolls"][0]["winnerStatus"] == "pending"
    assert result["requests"]["lolesportsEventDetailsPolls"][1]["winnerStatus"] == "present"
