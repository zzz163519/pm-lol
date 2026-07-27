import numpy as np

from pm_lol.vision.ocr import RapidOcrAdapter, _parse_value


class FakeEngine:
    def __init__(self, result):
        self.result = result

    def __call__(self, image, **kwargs):
        return self.result, None


def test_parse_clock_and_gold():
    assert _parse_value("06:49", "clock")[1] == 409
    assert _parse_value("11.5K", "gold")[1] == 11500


def test_parse_integer_common_ocr_substitutions():
    assert _parse_value("O", "integer")[1] == 0
    assert _parse_value("I", "integer")[1] == 1


def test_adapter_rejects_low_confidence_value():
    engine = FakeEngine([["10.6K", 0.4]])
    adapter = RapidOcrAdapter(engine, min_confidence=0.7)
    image = np.zeros((10, 10, 3), dtype=np.uint8)

    reading = adapter.read(image, "gold")

    assert reading.value == 10600
    assert reading.accepted is False
