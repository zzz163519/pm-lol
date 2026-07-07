import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "polymarket_discovery_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("polymarket_discovery_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_lol_event_slugs_dedupes_event_slugs_only():
    smoke = load_smoke_module()
    html = """
    /event/lol-blg-t1-2026-07-04
    /market/lol-blg-t1-2026-07-04-game1
    /event/lol-tsw-tes-2026-07-04
    /event/lol-blg-t1-2026-07-04
    """

    assert smoke.extract_lol_event_slugs(html) == [
        "lol-blg-t1-2026-07-04",
        "lol-tsw-tes-2026-07-04",
    ]


def test_filter_game_winner_markets_extracts_game_number_and_tokens():
    smoke = load_smoke_module()
    markets = [
        {
            "slug": "lol-blg-t1-2026-07-04-game1",
            "question": "LoL: Bilibili Gaming vs T1 - Game 1 Winner",
            "conditionId": "0xabc",
            "outcomes": '["Bilibili Gaming", "T1"]',
            "clobTokenIds": '["token-blg", "token-t1"]',
        },
        {
            "slug": "lol-blg-t1-2026-07-04-game1-any-player-penta-kill",
            "question": "Game 1: Any Player Penta Kill?",
        },
    ]

    winners = smoke.filter_game_winner_markets(markets)

    assert len(winners) == 1
    assert winners[0]["gameNumber"] == 1
    assert winners[0]["outcomes"] == ["Bilibili Gaming", "T1"]
    assert winners[0]["clobTokenIds"] == ["token-blg", "token-t1"]


def test_classify_network_error_is_stable():
    smoke = load_smoke_module()

    assert smoke.classify_error_message("OpenSSL SSL_connect: SSL_ERROR_SYSCALL") == "ssl_error"
    assert smoke.classify_error_message("Read timed out after 20s") == "timeout"
    assert smoke.classify_http_status(503) == "http_error"


def test_mapping_confidence_for_blg_t1_static_match():
    smoke = load_smoke_module()
    event = {
        "eventSlug": "lol-blg-t1-2026-07-04",
        "title": "LoL: Bilibili Gaming vs T1 (BO5) - Mid-Season Invitational Playoffs",
        "startTime": "2026-07-04T08:00:00Z",
        "teams": ["Bilibili Gaming", "T1"],
    }
    lolesports = {
        "ok": True,
        "metadata": {
            "matchId": "115570934355614527",
            "startTime": "2026-07-04T08:00:00Z",
            "teams": [
                {"name": "Bilibili Gaming", "code": "BLG"},
                {"name": "T1", "code": "T1"},
            ],
        },
    }

    markets = [
        {"gameNumber": 1},
        {"gameNumber": 2},
        {"gameNumber": 3},
        {"gameNumber": 4},
    ]

    candidate = smoke.build_mapping_candidate(event, markets, lolesports)

    assert candidate["mappingConfidence"] >= 0.9
    assert candidate["viable"] is True
    assert candidate["pendingLiveValidation"] is True


def test_mapping_candidate_includes_token_to_lolesports_side_sample():
    smoke = load_smoke_module()
    event = {
        "eventSlug": "lol-blg-t1-2026-07-04",
        "title": "LoL: Bilibili Gaming vs T1 (BO5) - Mid-Season Invitational Playoffs",
        "startTime": "2026-07-04T08:00:00Z",
        "teams": ["Bilibili Gaming", "T1"],
    }
    lolesports = {
        "ok": True,
        "metadata": {
            "matchId": "115570934355614527",
            "eventId": "115570934355614527",
            "startTime": "2026-07-04T08:00:00Z",
            "teams": [
                {"id": "99566404853854212", "name": "BILIBILI GAMING", "code": "BLG"},
                {"id": "98767991853197861", "name": "T1", "code": "T1"},
            ],
            "games": [
                {
                    "id": "115570934355614528",
                    "number": 1,
                    "teams": [
                        {"id": "99566404853854212", "side": "blue"},
                        {"id": "98767991853197861", "side": "red"},
                    ],
                }
            ],
        },
    }
    markets = [
        {
            "marketSlug": "lol-blg-t1-2026-07-04-game1",
            "question": "LoL: Bilibili Gaming vs T1 - Game 1 Winner",
            "conditionId": "0x5267",
            "gameNumber": 1,
            "outcomes": ["Bilibili Gaming", "T1"],
            "clobTokenIds": ["token-blg", "token-t1"],
        }
    ]

    candidate = smoke.build_mapping_candidate(event, markets, lolesports)

    assert candidate["sampleMappings"][0] == {
        "status": "mapped",
        "polymarketTitle": "LoL: Bilibili Gaming vs T1 - Game 1 Winner",
        "marketSlug": "lol-blg-t1-2026-07-04-game1",
        "conditionId": "0x5267",
        "tokenId": "token-blg",
        "outcome": "Bilibili Gaming",
        "lolesportsMatchId": "115570934355614527",
        "lolesportsEventId": "115570934355614527",
        "lolesportsGameId": "115570934355614528",
        "gameNumber": 1,
        "teamId": "99566404853854212",
        "teamName": "BILIBILI GAMING",
        "teamCode": "BLG",
        "teamSide": "blue",
        "mappingConfidence": 0.9625,
        "skipReason": None,
    }


def test_mapping_candidate_skips_token_side_sample_below_confidence_gate():
    smoke = load_smoke_module()
    event = {
        "eventSlug": "lol-unknown-t1-2026-07-04",
        "title": "LoL: Unknown Team vs T1 (BO5)",
        "startTime": "2026-07-04T08:00:00Z",
        "teams": ["Unknown Team", "T1"],
    }
    lolesports = {
        "ok": True,
        "metadata": {
            "matchId": "115570934355614527",
            "eventId": "115570934355614527",
            "startTime": "2026-07-04T08:00:00Z",
            "teams": [
                {"id": "99566404853854212", "name": "BILIBILI GAMING", "code": "BLG"},
                {"id": "98767991853197861", "name": "T1", "code": "T1"},
            ],
            "games": [
                {
                    "id": "115570934355614528",
                    "number": 1,
                    "teams": [
                        {"id": "99566404853854212", "side": "blue"},
                        {"id": "98767991853197861", "side": "red"},
                    ],
                }
            ],
        },
    }
    markets = [
        {
            "marketSlug": "lol-unknown-t1-2026-07-04-game1",
            "question": "LoL: Unknown Team vs T1 - Game 1 Winner",
            "conditionId": "0xskip",
            "gameNumber": 1,
            "outcomes": ["Unknown Team", "T1"],
            "clobTokenIds": ["token-unknown", "token-t1"],
        }
    ]

    candidate = smoke.build_mapping_candidate(event, markets, lolesports)

    assert candidate["sampleMappings"][0]["status"] == "skipped"
    assert candidate["sampleMappings"][0]["mappingConfidence"] < 0.90
    assert candidate["sampleMappings"][0]["skipReason"] == "mapping_confidence_below_0.90"


def test_mapping_candidate_uses_supplied_lolesports_match_id_for_confidence():
    smoke = load_smoke_module()
    event = {
        "eventSlug": "lol-blg-hle1-2026-07-09",
        "title": "LoL: Bilibili Gaming vs Hanwha Life Esports (BO5)",
        "startTime": "2026-07-09T08:00:00Z",
        "teams": ["Bilibili Gaming", "Hanwha Life Esports"],
    }
    lolesports = {
        "ok": True,
        "metadata": {
            "matchId": "115570934355614575",
            "eventId": "115570934355614575",
            "startTime": "2026-07-09T08:00:00Z",
            "teams": [
                {"id": "99566404853854212", "name": "BILIBILI GAMING", "code": "BLG"},
                {"id": "100205573495116443", "name": "Hanwha Life Esports", "code": "HLE"},
            ],
            "games": [
                {
                    "id": "115570934355614576",
                    "number": 1,
                    "teams": [
                        {"id": "99566404853854212", "side": "blue"},
                        {"id": "100205573495116443", "side": "red"},
                    ],
                },
                {"id": "115570934355614577", "number": 2, "teams": []},
                {"id": "115570934355614578", "number": 3, "teams": []},
                {"id": "115570934355614579", "number": 4, "teams": []},
            ],
        },
    }
    markets = [
        {
            "marketSlug": "lol-blg-hle1-2026-07-09-game1",
            "question": "LoL: Bilibili Gaming vs Hanwha Life Esports - Game 1 Winner",
            "conditionId": "0x86d9",
            "gameNumber": 1,
            "outcomes": ["Bilibili Gaming", "Hanwha Life Esports"],
            "clobTokenIds": ["token-blg", "token-hle"],
        },
        {"gameNumber": 2, "outcomes": [], "clobTokenIds": []},
        {"gameNumber": 3, "outcomes": [], "clobTokenIds": []},
        {"gameNumber": 4, "outcomes": [], "clobTokenIds": []},
    ]

    candidate = smoke.build_mapping_candidate(
        event,
        markets,
        lolesports,
        expected_match_id="115570934355614575",
    )

    assert candidate["mappingConfidence"] == 1.0
    assert candidate["sampleMappings"][0]["status"] == "mapped"
    assert candidate["sampleMappings"][0]["teamSide"] == "blue"


def test_mapping_candidate_alias_summary_uses_current_event_teams():
    smoke = load_smoke_module()
    event = {
        "eventSlug": "lol-ly-tsw-2026-07-08",
        "title": "LoL: LYON vs Team Secret Whales (BO5)",
        "startTime": "2026-07-08T03:00:00Z",
        "teams": ["LYON", "Team Secret Whales"],
    }
    lolesports = {
        "ok": True,
        "metadata": {
            "matchId": "115570934355614587",
            "eventId": "115570934355614587",
            "startTime": "2026-07-08T03:00:00Z",
            "teams": [
                {"id": "99566405941863385", "name": "LYON", "code": "LYON"},
                {"id": "113661839307879869", "name": "Team Secret Whales", "code": "TSW"},
            ],
            "games": [
                {
                    "id": "115570934355614588",
                    "number": 1,
                    "teams": [
                        {"id": "99566405941863385", "side": "blue"},
                        {"id": "113661839307879869", "side": "red"},
                    ],
                }
            ],
        },
    }
    markets = [
        {
            "marketSlug": "lol-ly-tsw-2026-07-08-game1",
            "question": "LoL: LYON vs Team Secret Whales - Game 1 Winner",
            "conditionId": "0x4334",
            "gameNumber": 1,
            "outcomes": ["LYON", "Team Secret Whales"],
            "clobTokenIds": ["token-lyon", "token-tsw"],
        }
    ]

    candidate = smoke.build_mapping_candidate(
        event,
        markets,
        lolesports,
        expected_match_id="115570934355614587",
    )

    assert candidate["teamAliasMapping"] == {
        "LYON": ["LYON"],
        "Team Secret Whales": ["Team Secret Whales", "TSW"],
    }
    assert candidate["sampleMappings"][1]["teamCode"] == "TSW"
    assert candidate["sampleMappings"][1]["teamSide"] == "red"
