import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cito_t1_g2_field_probe.py"


def load_probe_module():
    spec = importlib.util.spec_from_file_location("cito_t1_g2_field_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_target_match_recurses_schedule_and_prefers_t1_g2():
    probe = load_probe_module()

    match = probe.find_target_match(
        {
            "success": True,
            "data": {
                "matches": [
                    {"id": "other", "teams": [{"code": "BLG"}, {"code": "HLE"}]},
                    {
                        "id": "match-1",
                        "gameId": "game-1",
                        "startTime": "2026-07-08T08:00:00Z",
                        "teams": [{"code": "G2", "name": "G2 Esports"}, {"code": "T1", "name": "T1"}],
                    },
                ]
            },
        },
        ("T1", "G2"),
    )

    assert match["id"] == "match-1"
    assert match["gameId"] == "game-1"


def test_visual_state_field_summary_reports_present_missing_and_gold_diff():
    probe = load_probe_module()

    summary = probe.summarize_visual_state_fields(
        {
            "status": "live",
            "gameState": "in_game",
            "gameTimeFormatted": "12:34",
            "blueTeam": {
                "name": "G2 Esports",
                "tag": "G2",
                "gold": 24500,
                "kills": 4,
                "dragons": 1,
                "barons": 0,
                "towers": 2,
                "picks": ["Azir", "Vi"],
            },
            "redTeam": {
                "name": "T1",
                "tag": "T1",
                "gold": 23800,
                "kills": 3,
                "dragons": 0,
                "barons": 0,
                "towers": 1,
                "picks": ["Orianna", "Lee Sin"],
            },
            "winner": None,
        }
    )

    assert summary["teamIdentity"]["status"] == "present"
    assert summary["gold"]["status"] == "present"
    assert summary["gold"]["goldDiff"] == 700
    assert summary["objectives"]["status"] == "present"
    assert summary["kills"]["status"] == "present"
    assert summary["draftPicks"]["status"] == "present"
    assert summary["gameState"]["status"] == "present"
    assert summary["winner"]["status"] == "missing"


def test_request_frequency_summary_counts_rate_limit_and_request_rate():
    probe = load_probe_module()

    summary = probe.summarize_request_frequency(
        [
            {"observedAt": "2026-07-08T08:00:00Z", "statusCode": 200, "url": "https://api.citoapi.com/api/v1/lol/live"},
            {
                "observedAt": "2026-07-08T08:00:05Z",
                "statusCode": 200,
                "url": "https://api.citoapi.com/api/v1/lol/live/game-1/visual-state",
            },
            {"observedAt": "2026-07-08T08:00:10Z", "statusCode": 429, "url": "https://api.citoapi.com/api/v1/lol/live"},
        ]
    )

    assert summary["citoRequestCount"] == 3
    assert summary["status429Count"] == 1
    assert summary["minIntervalSec"] == 5.0
    assert summary["maxRequestsPerMinuteObserved"] == 3.0
    assert summary["requestBudgetPerMinute"] == 6
    assert summary["configuredMinIntervalSec"] == 10.0


def test_run_probe_stops_after_schedule_rate_limit(tmp_path):
    probe = load_probe_module()
    calls = []

    def fake_get(url, headers=None, timeout=20.0):
        calls.append(url)
        return {"success": False, "error": {"code": "RATE_LIMIT_EXCEEDED"}}, {
            "observedAt": "2026-07-08T08:00:00Z",
            "statusCode": 429,
            "url": url,
            "ok": False,
        }

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        duration_sec=60,
        poll_interval_sec=5,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T08:00:00Z",
    )

    assert calls == ["https://api.citoapi.com/api/v1/lol/schedule/today"]
    assert result["requestFrequency"]["status429Count"] == 1
    assert result["polling"]["iterations"] == 0


def test_run_probe_uses_coverage_game_id_for_visual_state(tmp_path):
    probe = load_probe_module()
    calls = []

    def fake_get(url, headers=None, timeout=20.0):
        calls.append(url)
        if url.endswith("/lol/schedule/today"):
            return {
                "matches": [
                    {
                        "matchId": "lol-match-1",
                        "teams": [{"code": "G2"}, {"code": "T1"}],
                    }
                ]
            }, {"observedAt": "2026-07-08T08:00:00Z", "statusCode": 200, "url": url, "ok": True}
        if url.endswith("/lol/live"):
            return {
                "status": "live",
                "data": [{"matchId": "lol-match-1", "team1": {"code": "G2"}, "team2": {"code": "T1"}}],
            }, {"observedAt": "2026-07-08T08:00:05Z", "statusCode": 200, "url": url, "ok": True}
        if url.endswith("/lol/matches/1/coverage"):
            return {
                "active_live_game_id": "lol-game-2",
                "coverage": {"numeric_live_state": True},
            }, {"observedAt": "2026-07-08T08:00:06Z", "statusCode": 200, "url": url, "ok": True}
        if url.endswith("/lol/live/2/visual-state"):
            return {
                "status": "live",
                "blueTeam": {"tag": "G2", "gold": 1000, "kills": 1, "dragons": 0, "barons": 0, "towers": 0},
                "redTeam": {"tag": "T1", "gold": 900, "kills": 0, "dragons": 0, "barons": 0, "towers": 0},
            }, {"observedAt": "2026-07-08T08:00:07Z", "statusCode": 200, "url": url, "ok": True}
        raise AssertionError(url)

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        duration_sec=0,
        poll_interval_sec=5,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T08:00:08Z",
    )

    assert "https://api.citoapi.com/api/v1/lol/live/1/visual-state" not in calls
    assert "https://api.citoapi.com/api/v1/lol/live/2/visual-state" in calls
    assert result["target"]["matchId"] == "1"
    assert result["target"]["gameId"] == "2"
    assert result["fieldCoverage"]["gold"]["status"] == "present"


def test_run_probe_paces_all_cito_endpoints_with_one_shared_budget(tmp_path):
    probe = load_probe_module()
    calls = []
    sleeps = []

    def fake_get(url, headers=None, timeout=20.0):
        calls.append(url)
        if url.endswith("/lol/schedule/today"):
            payload = {"matches": [{"matchId": "lol-match-1", "gameId": "lol-game-2", "teams": [{"code": "G2"}, {"code": "T1"}]}]}
        elif url.endswith("/lol/live/2/visual-state"):
            payload = {"status": "live", "blueTeam": {"tag": "G2"}, "redTeam": {"tag": "T1"}}
        else:
            raise AssertionError(url)
        return payload, {"observedAt": "2026-07-08T08:00:00Z", "statusCode": 200, "url": url, "ok": True}

    result = probe.run_probe(
        cito_api_key="secret",
        output_dir=tmp_path,
        target_teams=("T1", "G2"),
        duration_sec=0,
        poll_interval_sec=0,
        request_budget_per_min=6,
        http_get=fake_get,
        sleep=sleeps.append,
        now=lambda: "2026-07-08T08:00:00Z",
        monotonic=lambda: 0.0,
    )

    assert calls == [
        "https://api.citoapi.com/api/v1/lol/schedule/today",
        "https://api.citoapi.com/api/v1/lol/live/2/visual-state",
    ]
    assert sleeps == [10.0]
    assert result["polling"]["requestBudgetPerMinute"] == 6
    assert result["polling"]["minRequestIntervalSec"] == 10.0


def test_run_probe_rejects_budget_at_or_above_cito_limit(tmp_path):
    probe = load_probe_module()

    for budget in (0, 10, 60):
        try:
            probe.run_probe(
                cito_api_key="secret",
                output_dir=tmp_path,
                target_teams=("T1", "G2"),
                duration_sec=0,
                poll_interval_sec=0,
                request_budget_per_min=budget,
                http_get=lambda *args, **kwargs: ({}, {}),
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"budget {budget} should be rejected")
