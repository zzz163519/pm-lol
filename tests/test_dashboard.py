import json

from pm_lol.dashboard import build_dashboard_snapshot, render_dashboard_html
from pm_lol.replay_pipeline import run_replay
from pm_lol.storage import SCHEMA_VERSION


def test_dashboard_snapshot_contract_reads_phase1_sqlite(tmp_path):
    db_path = tmp_path / "replay.db"
    run_replay(db_path)

    snapshot = build_dashboard_snapshot(
        db_path,
        match_id="115548128963037587",
        game_id="115548128963037589",
        source="cito_visual_state",
    )

    assert snapshot["schemaVersion"] == SCHEMA_VERSION
    assert snapshot["filters"] == {
        "matchId": "115548128963037587",
        "gameId": "115548128963037589",
        "source": "cito_visual_state",
        "observedFrom": None,
        "observedTo": None,
    }
    assert len(snapshot["markets"]) == 1

    market = snapshot["markets"][0]
    assert market["mappingConfidence"] < 0.9
    assert market["marketStatus"] == "skipped_low_confidence"
    assert market["statusBadges"] == ["low_confidence"]
    assert market["yesQuote"]["bestBid"] == 0.791
    assert market["yesQuote"]["bestAsk"] == 0.801
    assert market["noQuote"]["bestBid"] == 0.199
    assert market["noQuote"]["bestAsk"] == 0.209

    assert snapshot["gameStates"] == []

    match_snapshot = build_dashboard_snapshot(
        db_path,
        match_id="115548128963037587",
        source="cito_visual_state",
    )
    game_state = match_snapshot["gameStates"][0]
    assert game_state["gameClock"] is None
    assert game_state["gold"] == {"blue": 26066, "red": 28132, "diff": -2066}
    assert game_state["objectives"]["redDragons"] == ["infernal", "mountain"]
    assert game_state["sourceStatus"] == "ok"

    assert match_snapshot["picks"]["blue"] == ["Vayne", "Trundle", "Cassiopeia", "Ziggs", "Shen"]
    assert snapshot["sourceStatusSummary"]["stale"] == 1
    assert snapshot["sourceStatusSummary"]["rate_limited"] == 1
    assert snapshot["collectorEvents"][0]["source"] == "cito_visual_state"

    json.dumps(snapshot)


def test_dashboard_snapshot_surfaces_missing_and_no_liquidity(tmp_path):
    db_path = tmp_path / "replay.db"
    run_replay(db_path)

    snapshot = build_dashboard_snapshot(
        db_path,
        match_id="unknown-match",
        game_id="unknown-game",
    )

    assert snapshot["markets"] == []
    assert snapshot["gameStates"] == []
    assert snapshot["picks"] == {"blue": [], "red": []}
    assert "missing" in snapshot["sourceStatusSummary"]


def test_dashboard_game_filter_excludes_other_game_markets(tmp_path):
    db_path = tmp_path / "replay.db"
    run_replay(db_path)

    unknown_game = build_dashboard_snapshot(
        db_path,
        match_id="115548128963037587",
        game_id="unknown-game",
    )
    live_state_game = build_dashboard_snapshot(
        db_path,
        match_id="115548128963037587",
        game_id="115548128963037588",
    )
    market_game = build_dashboard_snapshot(
        db_path,
        match_id="115548128963037587",
        game_id="115548128963037589",
    )

    assert unknown_game["markets"] == []
    assert unknown_game["gameStates"] == []
    assert live_state_game["markets"] == []
    assert len(live_state_game["gameStates"]) == 1
    assert len(market_game["markets"]) == 1
    assert market_game["markets"][0]["gameId"] == "115548128963037589"


def test_dashboard_html_smoke_renders_read_only_status_badges(tmp_path):
    db_path = tmp_path / "replay.db"
    run_replay(db_path)
    snapshot = build_dashboard_snapshot(db_path)

    html = render_dashboard_html(snapshot)

    assert "PM-LOL Read-only Dashboard" in html
    assert "KT Rolster Challengers" in html
    assert "Saigon Warriors" in html
    assert "mappingConfidence" in html
    assert "0.791" in html
    assert "0.801" in html
    assert "Game clock" in html
    assert "missing" in html
    assert "26,066" in html
    assert "28,132" in html
    assert "infernal" in html
    assert "Vayne" in html
    assert "low_confidence" in html
    assert "stale" in html
    assert "rate_limited" in html
    assert "Fair probability: disabled" in html
    assert "Polymarket orders: disabled" in html
    assert "wallet" not in html.lower()
    assert "private key" not in html.lower()
    assert "<button" not in html.lower()
