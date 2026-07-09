import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cito_live_polymarket_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("cito_live_polymarket_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_cito_api_key_prefers_env_file_without_logging_secret(tmp_path, monkeypatch):
    smoke = load_smoke_module()
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=ignored\nCITO_API_KEY=abc123\n", encoding="utf-8")

    monkeypatch.delenv("CITO_API_KEY", raising=False)

    loaded = smoke.load_cito_api_key(env_path)

    assert loaded == smoke.ApiKeyLoadResult(present=True, source=".env", length=6)


def test_no_match_poll_times_out_as_non_fatal_and_writes_raw_sample(tmp_path):
    smoke = load_smoke_module()
    calls = []

    def fake_get(url, headers=None, timeout=10.0):
        calls.append((url, headers))
        if url.endswith("/lol/schedule/today"):
            return {
                "success": True,
                "matches": [
                    {
                        "id": "match-1",
                        "gameId": None,
                        "officialEventId": "event-1",
                        "teams": [{"code": "G2"}, {"code": "T1"}],
                    }
                ],
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T02:40:00Z"}
        if url.endswith("/lol/live"):
            return {
                "success": True,
                "status": "no_match",
                "message": "No LoL match is live right now.",
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T02:40:01Z"}
        if "gamma-api.polymarket.com/events/slug" in url:
            return {
                "markets": [
                    {
                        "slug": "lol-g2-t1-2026-07-08-game1",
                        "question": "LoL: G2 Esports vs T1 - Game 1 Winner",
                        "conditionId": "0xgame1",
                        "outcomes": '["G2 Esports","T1"]',
                        "clobTokenIds": '["token-g2","token-t1"]',
                    }
                ]
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T02:40:02Z"}
        if "clob.polymarket.com/markets" in url:
            return {"markets": [{"condition_id": "0xgame1"}]}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T02:40:03Z",
            }
        raise AssertionError(url)

    result = smoke.run_smoke(
        cito_api_key="secret-key",
        output_dir=tmp_path,
        event_slugs=["lol-g2-t1-2026-07-08"],
        poll_timeout_sec=0,
        poll_interval_sec=0,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T02:40:04Z",
    )

    assert result["overallStatus"] == "no_match_timeout"
    assert result["auth"]["apiKeyPresent"] is True
    assert result["auth"]["apiKeyLength"] == 10
    assert result["fieldCoverage"]["gameClock"] == "missing_no_live_match"
    assert result["fieldCoverage"]["teamIdentity"] == "present"
    assert result["cito"]["live"]["status"] == "no_match"
    assert result["polymarket"]["status"] == "ok"
    assert result["timing"]["citoVsPolymarketDeltaSec"] == 2.0
    assert Path(result["rawSamplePaths"]["report"]).exists()
    assert Path(result["rawSamplePaths"]["dryRun"]).exists()
    assert json.loads(Path(result["rawSamplePaths"]["dryRun"]).read_text())["status"] == "no_match"
    assert calls[0][1]["x-api-key"] == "secret-key"


def test_live_game_fetches_visual_state_and_marks_field_coverage(tmp_path):
    smoke = load_smoke_module()

    def fake_get(url, headers=None, timeout=10.0):
        if url.endswith("/lol/schedule/today"):
            return {"success": True, "matches": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:00Z"}
        if url.endswith("/lol/live"):
            return {"success": True, "status": "live", "gameId": "game-123"}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:01Z",
            }
        if url.endswith("/lol/live/game-123/visual-state"):
            return {
                "gameId": "game-123",
                "status": "on_break",
                "reason": "broadcast_desk_or_break_detected",
                "sampleAgeSeconds": 17,
                "confidence": {"gold": 0, "kills": 0, "objectives": 0, "timer": 0},
                "dataQuality": {"numericLiveStats": "unavailable"},
                "gameState": "in_game",
                "gameTime": 123,
                "teams": [
                    {"name": "G2 Esports", "gold": 12000, "dragons": 1, "picks": ["Azir"]},
                    {"name": "T1", "gold": 11800, "barons": 0, "picks": ["Orianna"]},
                ],
                "winner": None,
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:02Z"}
        if url.endswith("/lol/matches/game-123/coverage"):
            return {"success": True}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:02Z"}
        if "gamma-api.polymarket.com/events/slug" in url:
            return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:03Z"}
        return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:04Z"}

    result = smoke.run_smoke(
        cito_api_key="secret-key",
        output_dir=tmp_path,
        event_slugs=["lol-g2-t1-2026-07-08"],
        poll_timeout_sec=15,
        poll_interval_sec=0,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T03:00:05Z",
    )

    assert result["overallStatus"] == "live_sample_collected"
    assert result["cito"]["visualState"]["gameId"] == "game-123"
    assert result["cito"]["visualState"]["status"] == "on_break"
    assert result["cito"]["visualState"]["reason"] == "broadcast_desk_or_break_detected"
    assert result["cito"]["visualState"]["sampleAgeSeconds"] == 17
    assert result["cito"]["visualState"]["confidence"] == {
        "gold": 0,
        "kills": 0,
        "objectives": 0,
        "timer": 0,
    }
    assert result["cito"]["visualState"]["dataQuality"] == {"numericLiveStats": "unavailable"}
    assert result["cito"]["visualState"]["liveNumericStatsAvailable"] is False
    assert result["fieldCoverage"] == {
        "gameClock": "present",
        "gold": "present",
        "objectives": "present",
        "gameState": "present",
        "winner": "missing",
        "finalPicks": "present",
        "teamIdentity": "present",
    }
    assert Path(result["rawSamplePaths"]["visualState"]).exists()


def test_live_listed_match_id_is_discovered_from_cito_data_rows(tmp_path):
    smoke = load_smoke_module()

    def fake_get(url, headers=None, timeout=10.0):
        if url.endswith("/lol/schedule/today"):
            return {"success": True, "data": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:00Z"}
        if url.endswith("/lol/live"):
            return {
                "success": True,
                "status": "live",
                "data": [
                    {
                        "matchId": "115570934355614587",
                        "coverage": {
                            "precheck_endpoint": "/api/v1/lol/matches/115570934355614587/coverage"
                        },
                    }
                ],
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:01Z"}
        if url.endswith("/lol/live/115570934355614587/visual-state"):
            return {"error": "numeric live state not ready"}, {
                "ok": False,
                "statusCode": 404,
                "observedAt": "2026-07-08T03:00:02Z",
            }
        if url.endswith("/lol/matches/115570934355614587/coverage"):
            return {"success": True}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:02Z"}
        if "gamma-api.polymarket.com/events/slug" in url:
            return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:03Z"}
        return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:04Z"}

    result = smoke.run_smoke(
        cito_api_key="secret-key",
        output_dir=tmp_path,
        event_slugs=["lol-ly-tsw-2026-07-08"],
        poll_timeout_sec=15,
        poll_interval_sec=0,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T03:00:05Z",
    )

    assert result["cito"]["live"]["gameId"] == "115570934355614587"
    assert result["cito"]["visualState"]["request"]["statusCode"] == 404
    assert result["overallStatus"] == "live_visual_state_unavailable"


def test_visual_state_not_ready_is_not_counted_as_collected(tmp_path):
    smoke = load_smoke_module()

    def fake_get(url, headers=None, timeout=10.0):
        if url.endswith("/lol/schedule/today"):
            return {"success": True, "data": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:00Z"}
        if url.endswith("/lol/live"):
            return {"success": True, "status": "live", "data": [{"matchId": "match-1"}]}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:01Z",
            }
        if url.endswith("/lol/matches/match-1/coverage"):
            return {"coverage": {"numeric_live_state": False}}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:02Z",
            }
        if url.endswith("/lol/live/match-1/visual-state"):
            return {"success": True, "status": "not_ready", "data": None}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:03Z",
            }
        if url.endswith("/lol/live/match-1/stats") or url.endswith("/lol/games/match-1/postgame"):
            return {"success": True, "data": None}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:04Z",
            }
        if "gamma-api.polymarket.com/events/slug" in url:
            return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:05Z"}
        return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:06Z"}

    result = smoke.run_smoke(
        cito_api_key="secret-key",
        output_dir=tmp_path,
        event_slugs=["lol-ly-tsw-2026-07-08"],
        poll_timeout_sec=15,
        poll_interval_sec=0,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T03:00:07Z",
    )

    assert result["overallStatus"] == "live_visual_state_not_ready"
    assert result["cito"]["visualState"]["ready"] is False
    assert Path(result["rawSamplePaths"]["coverage"]).exists()
    assert Path(result["rawSamplePaths"]["stats"]).exists()
    assert Path(result["rawSamplePaths"]["postgame"]).exists()


def test_coverage_game_id_is_used_for_visual_state_when_live_returns_match_id(tmp_path):
    smoke = load_smoke_module()

    def fake_get(url, headers=None, timeout=10.0):
        if url.endswith("/lol/schedule/today"):
            return {"success": True, "data": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:00Z"}
        if url.endswith("/lol/live"):
            return {"success": True, "status": "live", "data": [{"matchId": "match-1"}]}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:01Z",
            }
        if url.endswith("/lol/matches/match-1/coverage"):
            return {"games": [{"esportsApiId": "game-1", "gameNumber": 1}]}, {
                "ok": True,
                "statusCode": 200,
                "observedAt": "2026-07-08T03:00:02Z",
            }
        if url.endswith("/lol/live/game-1/visual-state"):
            return {
                "gameId": "game-1",
                "gameState": "in_game",
                "gameTime": 10,
                "teams": [{"name": "LYON", "gold": 1000, "dragons": 0}],
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:03Z"}
        if "gamma-api.polymarket.com/events/slug" in url:
            return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:05Z"}
        return {"markets": []}, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:06Z"}

    result = smoke.run_smoke(
        cito_api_key="secret-key",
        output_dir=tmp_path,
        event_slugs=["lol-ly-tsw-2026-07-08"],
        poll_timeout_sec=15,
        poll_interval_sec=0,
        http_get=fake_get,
        sleep=lambda _: None,
        now=lambda: "2026-07-08T03:00:07Z",
    )

    assert result["overallStatus"] == "live_sample_collected"
    assert result["cito"]["live"]["matchId"] == "match-1"
    assert result["cito"]["visualState"]["gameId"] == "game-1"
