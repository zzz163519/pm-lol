import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cito_latency_probe.py"


def load_probe_module():
    spec = importlib.util.spec_from_file_location("cito_latency_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_visual_state_extracts_clock_age_and_confidence_shape():
    probe = load_probe_module()

    summary = probe.summarize_visual_state(
        {
            "status": "provisional",
            "gameTimeSeconds": 492,
            "gameTimeFormatted": "8:12",
            "sampleAgeSeconds": 13,
            "confidence": {
                "gold": 1,
                "kills": 1,
                "objectives": 1,
                "timer": 1,
            },
            "blueTeam": {"tag": "LYON", "kills": 1, "gold": 14200, "towers": 1, "dragons": 1, "barons": 0},
            "redTeam": {"tag": "TSW", "kills": 1, "gold": 13500, "towers": 0, "dragons": 0, "barons": 0},
            "freshness": {"isFresh": True, "staleAfterSeconds": 45},
        },
        "2026-07-08T03:23:28.000Z",
    )

    assert summary["status"] == "provisional"
    assert summary["gameClock"] == "8:12"
    assert summary["gameTimeSeconds"] == 492
    assert summary["sampleAgeSeconds"] == 13
    assert summary["sourceLatencySec"] == 13
    assert summary["sourceLatencyBasis"] == "cito_sampleAgeSeconds_proxy"
    assert summary["blue"]["tag"] == "LYON"
    assert summary["red"]["gold"] == 13500
    assert summary["confidence"] == {"gold": 1, "kills": 1, "objectives": 1, "timer": 1}


def test_summarize_visual_state_marks_latency_not_computable_without_age():
    probe = load_probe_module()

    summary = probe.summarize_visual_state(
        {
            "status": "not_ready",
            "data": None,
            "message": "No accepted visual live state is available.",
        },
        "2026-07-08T03:23:28.000Z",
    )

    assert summary["gameClock"] is None
    assert summary["sampleAgeSeconds"] is None
    assert summary["sourceLatencySec"] is None
    assert summary["sourceLatencyBasis"] == "not_computable_no_cito_source_timestamp_or_sample_age"


def test_summarize_polymarket_book_uses_clob_timestamp_latency():
    probe = load_probe_module()

    summary = probe.summarize_polymarket_book(
        {
            "timestamp": "1783480929012",
            "bids": [{"price": "0.59", "size": "12"}],
            "asks": [{"price": "0.60", "size": "8"}],
        },
        "2026-07-08T03:22:08.632384Z",
        "LYON",
        "token-1",
    )

    assert summary["outcome"] == "LYON"
    assert summary["bestBid"] == 0.59
    assert summary["bestAsk"] == 0.6
    assert summary["bidCount"] == 1
    assert summary["askCount"] == 1
    assert summary["sourceTimestamp"] == "1783480929012"
    assert summary["sourceLatencySec"] == -0.38


def test_compute_latency_report_summarizes_proxy_ranges_and_confidence():
    probe = load_probe_module()

    report = probe.compute_latency_report(
        [
            {
                "metrics": {
                    "citoVisualState": {
                        "gameTimeSeconds": 397,
                        "sampleAgeSeconds": 22,
                        "sourceLatencySec": 22,
                        "confidence": {"gold": 1, "kills": 1, "objectives": 1, "timer": 1},
                    },
                    "polymarketBooks": [{"sourceLatencySec": 0.5}, {"sourceLatencySec": 1.5}],
                }
            },
            {
                "metrics": {
                    "citoVisualState": {
                        "gameTimeSeconds": 442,
                        "sampleAgeSeconds": 32,
                        "sourceLatencySec": 32,
                        "confidence": {"gold": 1, "kills": 1, "objectives": 1, "timer": 1},
                    },
                    "polymarketBooks": [{"sourceLatencySec": 0.25}, {"sourceLatencySec": 2.25}],
                }
            },
        ]
    )

    assert report["cito"]["sourceLatencySecProxy"]["min"] == 22
    assert report["cito"]["sourceLatencySecProxy"]["max"] == 32
    assert report["cito"]["gameTimeAdvancedSamples"] == 1
    assert report["cito"]["confidenceAssessment"]["observedUniqueValues"] == [
        {"gold": 1, "kills": 1, "objectives": 1, "timer": 1}
    ]
    assert report["cito"]["confidenceAssessment"]["trackedFieldsAlwaysOne"] is True
    assert report["cito"]["confidenceAssessment"]["conclusion"] == "tracked_fields_always_one_treat_as_unverified_not_calibrated"
    assert report["polymarket"]["sourceLatencySec"]["median"] == 1.0
