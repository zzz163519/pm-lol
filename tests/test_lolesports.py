import json
from pathlib import Path

from pm_lol.sources.lolesports import parse_event_details, parse_window


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


def load_sample(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_parse_event_details_extracts_match_and_games():
    payload = load_sample("lolesports-event-t1-gen-sample.json")

    match, games = parse_event_details(payload)

    assert match.match_id == "115548128963037587"
    assert match.league == "LCK"
    assert match.team_a_name == "T1"
    assert match.team_b_name == "Gen.G Esports"
    assert games[0].game_id == "115548128963037588"
    assert games[0].game_number == 1
    assert games[0].blue_team_id == "98767991853197861"
    assert games[0].red_team_id == "100205573495116443"


def test_parse_window_extracts_draft_and_game_state_snapshot():
    payload = load_sample("lolesports-window-t1-gen-g1-15m-sample.json")

    drafts, snapshot = parse_window(payload)

    assert len(drafts) == 10
    assert drafts[0].game_id == "115548128963037588"
    assert drafts[0].match_id == "115548128963037587"
    assert drafts[0].team_id == "98767991853197861"
    assert drafts[0].champion_id == "Vayne"
    assert drafts[0].side == "blue"
    assert snapshot.game_id == "115548128963037588"
    assert snapshot.timestamp == "2026-06-14T06:42:30.007Z"
    assert snapshot.game_state == "in_game"
    assert snapshot.blue_gold == 26066
    assert snapshot.red_gold == 28132
    assert snapshot.red_dragons == ["infernal", "mountain"]
