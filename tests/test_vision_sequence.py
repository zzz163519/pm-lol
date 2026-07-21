from pm_lol.vision.extractor import VisualFrameResult
from pm_lol.vision.matcher import ChampionMatch
from pm_lol.vision.ocr import OcrReading
from pm_lol.vision.sequence import VisualSequenceAggregator, observation_metrics


def _reading(value, confidence=0.99, accepted=True):
    return OcrReading(str(value), value, confidence, accepted)


def _frame(clock, *, tower=0, tower_confidence=0.5, champion="Annie"):
    fields = {
        "clock": _reading(clock),
        "leftGold": _reading(10000 + clock),
        "rightGold": _reading(10100 + clock),
        "leftKills": _reading(1),
        "rightKills": _reading(2),
        "leftTowers": _reading(tower, tower_confidence, False),
        "rightTowers": _reading(0, tower_confidence, False),
        "leftDragons": _reading(0, tower_confidence, False),
        "rightDragons": _reading(0, tower_confidence, False),
    }
    match = ChampionMatch(champion, 0.8, 0.6, 0.2, True, champion, True)
    groups = {"left": (match,), "right": ()}
    return VisualFrameResult(
        "layout", f"{clock}.jpg", 1920, 1080, "live_gameplay", _reading("LIVE"), fields,
        groups, {"left": (), "right": ()}, "partial_low_confidence", 0.8,
    )


def test_sequence_requires_repeated_low_confidence_objective_value():
    aggregator = VisualSequenceAggregator()

    single = aggregator.aggregate([_frame(60, tower=1)])
    repeated = aggregator.aggregate([_frame(60, tower=1), _frame(72, tower=1)])

    assert single.fields["leftTowers"].accepted is False
    assert repeated.fields["leftTowers"].accepted is True
    assert repeated.fields["leftTowers"].value == 1
    assert repeated.fields["leftTowers"].support == 2


def test_sequence_skips_non_advancing_frame_and_numeric_rollback():
    first = _frame(60, tower=1)
    stale = _frame(60, tower=9)
    rollback = _frame(72, tower=0)

    result = VisualSequenceAggregator().aggregate([first, stale, rollback])

    assert result.retained_frame_count == 2
    assert result.skipped_frames[0]["reason"] == "clock_not_advancing"
    assert result.fields["leftTowers"].accepted is False


def test_sequence_accepts_champion_only_after_cross_frame_geometric_agreement():
    first = _frame(60, champion="Annie")
    second = _frame(72, champion="Annie")

    result = VisualSequenceAggregator().aggregate([first, second])

    assert result.picks["left"][0].accepted is True
    assert result.picks["left"][0].value == "Annie"


def test_observation_metrics_records_capture_gap_without_claiming_source_latency():
    metrics = observation_metrics(
        [
            {"path": "01.jpg", "observedAt": "2026-07-21T07:00:00Z"},
            {"path": "02.jpg", "observedAt": "2026-07-21T07:00:05Z"},
            {"path": "03.jpg", "observedAt": "2026-07-21T07:00:25Z"},
        ],
        expected_interval_sec=5,
    )

    assert metrics["observedFrameCount"] == 3
    assert metrics["maxObservationGapSec"] == 20
    assert metrics["interruptions"] == [{"framePath": "03.jpg", "gapSec": 20}]
    assert metrics["sourceLatencySec"] is None
