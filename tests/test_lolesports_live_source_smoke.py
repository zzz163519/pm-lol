import json
from pathlib import Path

from pm_lol.collectors.lolesports_live_source_smoke import collect_live_source_smoke


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


class FakeClock:
    def __init__(self):
        self.values = iter(
            [
                "2026-06-14T06:42:35.007Z",
                "2026-06-14T06:42:36.007Z",
                "2026-06-14T06:42:37.007Z",
            ]
        )

    def __call__(self):
        return next(self.values)


def test_collect_live_source_smoke_writes_raw_samples_and_field_report(tmp_path):
    window_payload = json.loads((FIXTURES / "lolesports-window-t1-gen-g1-15m-sample.json").read_text())
    details_payload = json.loads((FIXTURES / "lolesports-details-t1-gen-g1-15m-sample.json").read_text())

    def fake_fetch(endpoint, game_id):
        assert endpoint in {"window", "details"}
        assert game_id == "115548128963037588"
        return (window_payload if endpoint == "window" else details_payload), {
            "ok": True,
            "statusCode": 200,
            "errorClass": None,
            "error": None,
        }

    report = collect_live_source_smoke(
        game_id="115548128963037588",
        output_dir=tmp_path,
        fetcher=fake_fetch,
        now=FakeClock(),
    )

    assert report["source"] == "lolesports_livestats"
    assert report["gameId"] == "115548128963037588"
    assert report["overallOk"] is True
    assert report["observedAt"] == "2026-06-14T06:42:35.007Z"
    assert report["fieldCoverage"] == {
        "finalPicks": "present",
        "gameClock": "derived_from_frame_timestamp_only",
        "gold": "present",
        "objectives": "present",
        "gameState": "present",
    }
    assert report["endpoints"]["window"]["sourceTimestamp"] == "2026-06-14T06:42:30.007Z"
    assert report["endpoints"]["window"]["sourceLatencySec"] == 5.0
    assert report["endpoints"]["details"]["sourceTimestamp"] == "2026-06-14T06:42:30.007Z"
    assert report["endpoints"]["details"]["sourceLatencySec"] == 6.0
    assert report["limitations"] == ["gameClock is not explicit; only derivable from frame timestamps."]
    assert report["failureReasons"] == []

    raw_paths = report["rawSamplePaths"]
    assert sorted(raw_paths) == ["details", "report", "window"]
    for path in raw_paths.values():
        assert Path(path).exists()

    persisted = json.loads(Path(raw_paths["report"]).read_text())
    assert persisted["endpoints"]["window"]["hasRawSample"] is True


def test_collect_live_source_smoke_records_failures_without_fake_success(tmp_path):
    def fake_fetch(endpoint, game_id):
        return None, {
            "ok": False,
            "statusCode": 204,
            "errorClass": "empty_body",
            "error": "no live body",
        }

    report = collect_live_source_smoke(
        game_id="missing-live-game",
        output_dir=tmp_path,
        fetcher=fake_fetch,
        now=lambda: "2026-07-08T00:00:00Z",
    )

    assert report["overallOk"] is False
    assert report["fieldCoverage"] == {
        "finalPicks": "missing",
        "gameClock": "missing",
        "gold": "missing",
        "objectives": "missing",
        "gameState": "missing",
    }
    assert report["endpoints"]["window"]["sourceTimestamp"] is None
    assert report["endpoints"]["window"]["sourceLatencySec"] is None
    assert report["failureReasons"] == [
        "window failed: empty_body",
        "details failed: empty_body",
        "required field finalPicks missing",
        "required field gold missing",
        "required field objectives missing",
        "required field gameState missing",
        "gameClock cannot be derived because no source frame timestamp was present.",
    ]
    assert report["rawSamplePaths"]["window"] is None
    assert Path(report["rawSamplePaths"]["report"]).exists()
