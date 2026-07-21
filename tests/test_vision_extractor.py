from pathlib import Path

import cv2
import numpy as np

from pm_lol.vision.extractor import VisualFrameExtractor, _constrain_counter
from pm_lol.vision.layout import load_layout
from pm_lol.vision.matcher import ChampionMatch
from pm_lol.vision.ocr import OcrReading


class FakeOcr:
    def read(self, image, kind):
        values = {"text": "LIVE", "clock": 60, "gold": 10000, "integer": 0}
        return OcrReading(str(values[kind]), values[kind], 0.99, True)


class RejectingMatcher:
    def match(self, image):
        return ChampionMatch(None, 0.4, 0.39, 0.01, False)


class ObjectiveTimerOcr(FakeOcr):
    def read(self, image, kind):
        if kind == "text":
            return OcrReading("4:26", "4:26", 0.99, True)
        return super().read(image, kind)


def test_source_status_rejects_frame_without_accepted_bp(tmp_path: Path):
    frame_path = tmp_path / "frame.jpg"
    assert cv2.imwrite(str(frame_path), np.zeros((1080, 1920, 3), dtype=np.uint8))
    extractor = VisualFrameExtractor(
        layout=load_layout("configs/vision/kespa_2026_1920x1080.json"),
        ocr=FakeOcr(),
        champion_matcher=RejectingMatcher(),
    )

    result = extractor.extract(frame_path)

    assert result.screen_state == "live_gameplay"
    assert result.source_status == "partial_low_confidence"


def test_core_scoreboard_keeps_live_frame_when_indicator_is_objective_timer(tmp_path: Path):
    frame_path = tmp_path / "frame.jpg"
    assert cv2.imwrite(str(frame_path), np.zeros((1080, 1920, 3), dtype=np.uint8))
    extractor = VisualFrameExtractor(
        layout=load_layout("configs/vision/kespa_2026_1920x1080.json"),
        ocr=ObjectiveTimerOcr(),
        champion_matcher=RejectingMatcher(),
    )

    result = extractor.extract(frame_path)

    assert result.screen_state == "live_gameplay_scoreboard_verified"
    assert result.fields["clock"].accepted is True


def test_dragon_counter_discards_adjacent_zero_glyph():
    reading = _constrain_counter("rightDragons", OcrReading("30", 30, 0.98, True))

    assert reading.value == 3
    assert reading.accepted is True
