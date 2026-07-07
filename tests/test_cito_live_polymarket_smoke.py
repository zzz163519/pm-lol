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
                "gameState": "in_game",
                "gameTime": 123,
                "teams": [
                    {"name": "G2 Esports", "gold": 12000, "dragons": 1, "picks": ["Azir"]},
                    {"name": "T1", "gold": 11800, "barons": 0, "picks": ["Orianna"]},
                ],
                "winner": None,
            }, {"ok": True, "statusCode": 200, "observedAt": "2026-07-08T03:00:02Z"}
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
