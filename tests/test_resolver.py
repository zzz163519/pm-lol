import sqlite3
from pathlib import Path

from pm_lol.models import Game, Market, Match
from pm_lol.resolvers.market_match_resolver import (
    build_mapping_artifact,
    resolve_market_attempt,
    resolve_market_to_game,
    resolve_pending_markets,
    team_name_confidence,
)
from pm_lol.storage import SQLiteStorage


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


def test_team_name_confidence_matches_common_alias():
    assert team_name_confidence("KT", "kt-rolster") >= 0.9


def test_team_name_confidence_caps_academy_challengers_youth_substrings():
    assert team_name_confidence("KT Rolster", "KT Rolster Challengers") < 0.9
    assert team_name_confidence("Example", "Example Academy") < 0.9
    assert team_name_confidence("Example", "Example Youth") < 0.9


def test_team_name_confidence_matches_lolesports_code_alias():
    assert team_name_confidence("Bilibili Gaming", "BLG") >= 0.9


def test_resolver_maps_market_to_game_when_confidence_is_high():
    market = Market(
        market_id="2530922",
        condition_id="0x56243f",
        slug="lol-ktc-sgw-2026-06-15-game2",
        title="LoL: KT Rolster Challengers vs Saigon Warriors - Game 2 Winner",
        outcomes=["KT", "Saigon Warriors"],
        token_ids=["100172", "452377"],
        raw={"startTime": "2026-06-15T08:00:00Z"},
    )
    match = Match(
        match_id="match-1",
        league="Asia Masters",
        team_a_id="ktc",
        team_a_name="kt-rolster",
        team_b_id="sgw",
        team_b_name="Saigon Warriors",
        start_time="2026-06-15T08:00:00Z",
    )
    game = Game(
        game_id="game-2",
        match_id="match-1",
        game_number=2,
        blue_team_id="ktc",
        red_team_id="sgw",
        state="unstarted",
    )

    resolved = resolve_market_to_game(market, match, [game])

    assert resolved is not None
    assert resolved.market_id == "2530922"
    assert resolved.game_id == "game-2"
    assert resolved.game_number == 2
    assert resolved.blue_team_id == "ktc"
    assert resolved.red_team_id == "sgw"
    assert resolved.mapping_confidence >= 0.9


def test_resolver_attempt_maps_tokens_to_lolesports_team_sides():
    market = Market(
        market_id="blg-hle-g1",
        condition_id="0xblghle",
        slug="lol-blg-hle1-2026-07-09-game1",
        title="LoL: Bilibili Gaming vs Hanwha Life Esports - Game 1 Winner",
        outcomes=["Bilibili Gaming", "Hanwha Life Esports"],
        token_ids=["blg-token", "hle-token"],
        raw={"startTime": "2026-07-09T08:00:00Z"},
    )
    match = Match(
        match_id="115570934355614575",
        league="MSI",
        team_a_id="100205573496804586",
        team_a_name="Hanwha Life Esports",
        team_b_id="99566404853854212",
        team_b_name="BLG",
        start_time="2026-07-09T08:00:00Z",
    )
    game = Game(
        game_id="115570934355614576",
        match_id=match.match_id,
        game_number=1,
        blue_team_id="100205573496804586",
        red_team_id="99566404853854212",
        state="unstarted",
    )

    attempt = resolve_market_attempt(market, match, [game])

    assert attempt.status == "mapped"
    assert attempt.skip_reason is None
    assert attempt.mapping_confidence >= 0.9
    assert [
        {
            "tokenOutcome": mapping.token_outcome,
            "tokenId": mapping.token_id,
            "teamSide": mapping.team_side,
            "teamId": mapping.team_id,
        }
        for mapping in attempt.token_mappings
    ] == [
        {
            "tokenOutcome": "Bilibili Gaming",
            "tokenId": "blg-token",
            "teamSide": "red",
            "teamId": "99566404853854212",
        },
        {
            "tokenOutcome": "Hanwha Life Esports",
            "tokenId": "hle-token",
            "teamSide": "blue",
            "teamId": "100205573496804586",
        },
    ]


def test_resolver_skips_low_confidence_market():
    market = Market(
        market_id="bad-market",
        condition_id="0xbad",
        slug="lol-abc-def-game1",
        title="LoL: Unknown Team vs Other Team - Game 1 Winner",
        outcomes=["Unknown Team", "Other Team"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )

    assert resolve_market_to_game(market, match, [game]) is None


def test_resolver_skips_challengers_false_positive_even_with_one_exact_side():
    market = Market(
        market_id="kt-false-positive",
        condition_id="0xkt",
        slug="lol-kt-gen-2026-06-14-game1",
        title="LoL: KT Rolster vs Gen.G Esports - Game 1 Winner",
        outcomes=["KT Rolster", "Gen.G Esports"],
        token_ids=["kt", "gen"],
        raw={"startTime": "2026-06-14T08:00:00Z"},
    )
    match = Match(
        match_id="match-1",
        league="LCK CL",
        team_a_id="ktc",
        team_a_name="KT Rolster Challengers",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
        start_time="2026-06-14T08:00:00Z",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="ktc",
        red_team_id="gen",
        state="unstarted",
    )

    attempt = resolve_market_attempt(market, match, [game])

    assert attempt.status == "skipped"
    assert attempt.skip_reason == "team_mismatch"
    assert attempt.resolved_market is None
    assert resolve_market_to_game(market, match, [game]) is None


def test_resolver_attempt_records_team_mismatch_skip_reason():
    market = Market(
        market_id="bad-market",
        condition_id="0xbad",
        slug="lol-abc-def-game1",
        title="LoL: Unknown Team vs Other Team - Game 1 Winner",
        outcomes=["Unknown Team", "Other Team"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )

    attempt = resolve_market_attempt(market, match, [game])

    assert attempt.status == "skipped"
    assert attempt.resolved_market is None
    assert attempt.mapping_confidence < 0.9
    assert attempt.skip_reason == "team_mismatch"


def test_resolver_attempt_records_ambiguous_game_number_skip_reason():
    market = Market(
        market_id="series-market",
        condition_id="0xseries",
        slug="lol-t1-gen-2026-06-14",
        title="LoL: T1 vs Gen.G Esports - Series Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )

    attempt = resolve_market_attempt(market, match, [])

    assert attempt.status == "skipped"
    assert attempt.skip_reason == "ambiguous_game_number"


def test_resolver_attempt_records_time_mismatch_skip_reason():
    market = Market(
        market_id="blg-t1-g1",
        condition_id="0xblgt1",
        slug="lol-blg-t1-2026-07-04-game1",
        title="LoL: Bilibili Gaming vs T1 - Game 1 Winner",
        outcomes=["Bilibili Gaming", "T1"],
        token_ids=["blg", "t1"],
        raw={"startTime": "2026-07-04T06:15:00Z"},
    )
    match = Match(
        match_id="115570934355614527",
        league="MSI",
        team_a_id="98767991853197861",
        team_a_name="T1",
        team_b_id="99566404853854212",
        team_b_name="BILIBILI GAMING",
        start_time="2026-07-04T08:00:00Z",
    )
    game = Game(
        game_id="115570934355614528",
        match_id=match.match_id,
        game_number=1,
        blue_team_id="98767991853197861",
        red_team_id="99566404853854212",
        state="completed",
    )

    attempt = resolve_market_attempt(market, match, [game])

    assert attempt.status == "skipped"
    assert attempt.skip_reason == "time_mismatch"


def test_resolver_attempt_skips_missing_start_time_when_time_is_required():
    market = Market(
        market_id="no-time",
        condition_id="0xnotime",
        slug="lol-t1-gen-2026-06-14-game1",
        title="LoL: T1 vs Gen.G Esports - Game 1 Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["t1", "gen"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
        start_time="2026-06-14T08:00:00Z",
    )
    game = Game(
        game_id="game-1",
        match_id=match.match_id,
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )

    attempt = resolve_market_attempt(market, match, [game], require_start_time=True)

    assert attempt.status == "skipped"
    assert attempt.skip_reason == "missing_start_time"


def test_resolver_attempt_skips_token_id_length_mismatch():
    market = Market(
        market_id="short-tokens",
        condition_id="0xshort",
        slug="lol-t1-gen-2026-06-14-game1",
        title="LoL: T1 vs Gen.G Esports - Game 1 Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["only-one-token"],
        raw={"startTime": "2026-06-14T08:00:00Z"},
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
        start_time="2026-06-14T08:00:00Z",
    )
    game = Game(
        game_id="game-1",
        match_id=match.match_id,
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )

    attempt = resolve_market_attempt(market, match, [game])

    assert attempt.status == "skipped"
    assert attempt.skip_reason == "ambiguous_token_outcomes"


def test_resolve_pending_markets_skips_ambiguous_match_candidates(tmp_path):
    db_path = tmp_path / "resolver.db"
    storage = SQLiteStorage(db_path)
    market = Market(
        market_id="m-ambiguous",
        condition_id="0xambiguous",
        slug="lol-t1-gen-2026-06-14-game1",
        title="LoL: T1 vs Gen.G Esports - Game 1 Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["t1", "gen"],
        raw={"startTime": "2026-06-14T08:00:00Z"},
    )
    for suffix in ("a", "b"):
        match = Match(
            match_id=f"match-{suffix}",
            league="LCK",
            team_a_id=f"t1-{suffix}",
            team_a_name="T1",
            team_b_id=f"gen-{suffix}",
            team_b_name="Gen.G Esports",
            start_time="2026-06-14T08:00:00Z",
        )
        game = Game(
            game_id=f"game-{suffix}",
            match_id=match.match_id,
            game_number=1,
            blue_team_id=f"t1-{suffix}",
            red_team_id=f"gen-{suffix}",
            state="unstarted",
        )
        storage.upsert_match(match)
        storage.upsert_game(game)
    storage.upsert_market(market)

    summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT market_status, skip_reason, mapping_confidence
            FROM resolved_markets WHERE market_id = 'm-ambiguous'
            """
        ).fetchall()

    assert summary == {"markets_seen": 1, "resolved": 0, "skipped": 1}
    assert rows == [("skipped", "ambiguous_match_candidates", 1.0)]


def test_resolve_pending_markets_writes_high_confidence_mapping(tmp_path):
    db_path = tmp_path / "resolver.db"
    storage = SQLiteStorage(db_path)
    market = Market(
        market_id="m1",
        condition_id="0xmatch",
        slug="lol-t1-gen-2026-06-14-game1",
        title="LoL: T1 vs Gen.G Esports - Game 1 Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["yes", "no"],
        raw={"startTime": "2026-06-14T08:00:00Z"},
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
        start_time="2026-06-14T08:00:00Z",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )
    storage.upsert_market(market)
    storage.upsert_match(match)
    storage.upsert_game(game)

    summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT mapping_confidence, market_status, skip_reason, raw_mapping_json
            FROM resolved_markets WHERE market_id = 'm1'
            """
        ).fetchone()

    assert summary == {"markets_seen": 1, "resolved": 1, "skipped": 0}
    assert row[0] >= 0.9
    assert row[1] == "active"
    assert row[2] is None
    assert "tokenMappings" in row[3]


def test_resolve_pending_markets_persists_blue_red_token_ids_as_first_class_columns(tmp_path):
    db_path = tmp_path / "resolver.db"
    storage = SQLiteStorage(db_path)
    market = Market(
        market_id="m-side",
        condition_id="0xside",
        slug="lol-blg-hle-2026-07-09-game1",
        title="LoL: Bilibili Gaming vs Hanwha Life Esports - Game 1 Winner",
        outcomes=["Bilibili Gaming", "Hanwha Life Esports"],
        token_ids=["blg-token", "hle-token"],
        raw={"startTime": "2026-07-09T08:00:00Z"},
    )
    match = Match(
        match_id="match-side",
        league="MSI",
        team_a_id="hle",
        team_a_name="Hanwha Life Esports",
        team_b_id="blg",
        team_b_name="BLG",
        start_time="2026-07-09T08:00:00Z",
    )
    game = Game(
        game_id="game-side-1",
        match_id="match-side",
        game_number=1,
        blue_team_id="hle",
        red_team_id="blg",
        state="unstarted",
    )
    storage.upsert_market(market)
    storage.upsert_match(match)
    storage.upsert_game(game)

    summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT blue_token_id, red_token_id
            FROM resolved_markets WHERE market_id = 'm-side'
            """
        ).fetchone()

    assert summary == {"markets_seen": 1, "resolved": 1, "skipped": 0}
    assert row == ("hle-token", "blg-token")


def test_resolve_pending_markets_persists_skip_attempt(tmp_path):
    db_path = tmp_path / "resolver.db"
    storage = SQLiteStorage(db_path)
    market = Market(
        market_id="m-skip",
        condition_id="0xskip",
        slug="lol-t1-gen-2026-06-14",
        title="LoL: T1 vs Gen.G Esports - Series Winner",
        outcomes=["T1", "Gen.G Esports"],
        token_ids=["yes", "no"],
    )
    match = Match(
        match_id="match-1",
        league="LCK",
        team_a_id="t1",
        team_a_name="T1",
        team_b_id="gen",
        team_b_name="Gen.G Esports",
    )
    game = Game(
        game_id="game-1",
        match_id="match-1",
        game_number=1,
        blue_team_id="t1",
        red_team_id="gen",
        state="unstarted",
    )
    storage.upsert_market(market)
    storage.upsert_match(match)
    storage.upsert_game(game)

    summary = resolve_pending_markets(storage)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT market_status, skip_reason, mapping_confidence
            FROM resolved_markets WHERE market_id = 'm-skip'
            """
        ).fetchone()

    assert summary == {"markets_seen": 1, "resolved": 0, "skipped": 1}
    assert row == ("skipped", "ambiguous_game_number", 0.0)


def test_build_mapping_artifact_records_multiple_fixture_outcomes():
    artifact = build_mapping_artifact(
        [
            FIXTURES / "phase0-closure-blg-hle-mapping-2026-07-08.json",
            FIXTURES / "cito-ly-tsw-prematch-mapping-2026-07-08.json",
            FIXTURES / "blg-t1-prematch-mapping-smoke.json",
        ]
    )

    assert artifact["scope"] == "CAL-68 MarketResolver v1 fixture regression"
    assert len(artifact["samples"]) == 3
    assert {sample["status"] for sample in artifact["samples"]} == {"mapped", "skipped"}
    assert any(sample["skipReason"] == "mapping_confidence_below_0.90" for sample in artifact["samples"])
    assert artifact["summary"]["sampleCount"] == 3
    assert artifact["summary"]["availabilityStatus"] == "insufficient_market"
    mapped = [sample for sample in artifact["samples"] if sample["status"] == "mapped"]
    assert len(mapped) == 2
    assert all(sample["mappingConfidence"] >= 0.9 for sample in mapped)
    assert all(
        {"marketSlug", "matchId", "gameId", "teamSide", "tokenOutcome", "tokenId", "mappingConfidence", "skipReason"}
        <= set(record)
        for sample in artifact["samples"]
        for record in sample["records"]
    )
