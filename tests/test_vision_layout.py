import json
from pathlib import Path

import pytest

from pm_lol.vision.layout import BroadcastLayout, Region, load_layout


LAYOUT_PATH = Path("configs/vision/kespa_2026_1920x1080.json")


def test_kespa_layout_has_required_regions():
    layout = load_layout(LAYOUT_PATH)

    assert layout.layout_id == "kespa_2026_1920x1080"
    assert layout.ddragon_version == "16.14.1"
    assert len(layout.picks["left"]) == len(layout.picks["right"]) == 5
    assert len(layout.bans["left"]) == len(layout.bans["right"]) == 5


def test_region_scales_to_half_resolution():
    region = Region(100, 200, 40, 60)
    assert region.scale(1920, 1080, 960, 540) == Region(50, 100, 20, 30)


def test_layout_rejects_missing_pick_slot():
    payload = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    payload["regions"]["picks"]["left"].pop()

    with pytest.raises(ValueError, match="five pick regions"):
        BroadcastLayout.from_dict(payload)
