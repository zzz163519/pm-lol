from pm_lol.vision.temporal import TemporalConsensus


def test_temporal_consensus_requires_cross_frame_agreement():
    consensus = TemporalConsensus[str](window_size=3, min_samples=2, min_agreement=2 / 3)

    assert consensus.add("Annie").accepted is False
    assert consensus.add("Annie").accepted is True
    result = consensus.add("Ahri")

    assert result.accepted is True
    assert result.value == "Annie"
    assert result.agreement == 2 / 3


def test_temporal_consensus_ignores_unknown_samples():
    consensus = TemporalConsensus[int](window_size=3, min_samples=2)

    assert consensus.add(None).sample_count == 0
    consensus.add(3)
    assert consensus.add(3).value == 3
