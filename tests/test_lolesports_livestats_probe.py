import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lolesports_t1_g2_livestats_probe.py"
SPEC = importlib.util.spec_from_file_location("lolesports_livestats_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def event(event_id, start_time, left, right):
    return {
        "id": event_id,
        "startTime": start_time,
        "match": {
            "id": event_id,
            "teams": [
                {"name": left, "code": left[:3].upper()},
                {"name": right, "code": right[:3].upper()},
            ],
        },
    }


def test_find_target_event_uses_expected_start_to_disambiguate_recurring_matchup():
    old = event("old", "2026-07-20T06:00:00Z", "Hanwha Life Esports", "Gen.G Esports")
    target = event("target", "2026-07-21T06:00:00Z", "Hanwha Life Esports", "Gen.G Esports")
    payload = {"data": {"schedule": {"events": [old, target]}}}

    found = probe.find_target_event(
        payload,
        ("Hanwha Life Esports", "Gen.G Esports"),
        "2026-07-21T06:00:00Z",
    )

    assert found["id"] == "target"


def test_find_target_event_rejects_team_match_when_expected_start_does_not_match():
    payload = {
        "data": {
            "events": [
                event("wrong-window", "2026-07-20T06:00:00Z", "Hanwha Life Esports", "Gen.G Esports")
            ]
        }
    }

    found = probe.find_target_event(
        payload,
        ("Hanwha Life Esports", "Gen.G Esports"),
        "2026-07-21T06:00:00Z",
    )

    assert found is None


def test_field_coverage_falls_back_to_details_for_final_picks():
    participants = [{"championId": str(index)} for index in range(5)]
    details = {
        "gameMetadata": {
            "blueTeamMetadata": {"participantMetadata": participants},
            "redTeamMetadata": {"participantMetadata": participants},
        }
    }

    coverage = probe.field_coverage({}, details, None)

    assert coverage["draftPicks"]["status"] == "present"
    assert len(coverage["draftPicks"]["sample"]["blue"]) == 5


def test_slugify_makes_target_specific_artifact_names_safe():
    assert probe.slugify("Gen.G Esports") == "gen-g-esports"
    assert probe.slugify("Hanwha Life Esports") == "hanwha-life-esports"
