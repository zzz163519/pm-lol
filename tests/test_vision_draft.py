import json
from pathlib import Path

import cv2
import numpy as np

from pm_lol.vision.cdragon import CDragonChampionSplashStore, CDragonChampionTileStore
from pm_lol.vision.ddragon import ChampionAsset
from pm_lol.vision.draft import (
    DraftChampionMatcher,
    DraftFrameResult,
    DraftSequenceAggregator,
    load_draft_layout,
)
from pm_lol.vision.matcher import ChampionMatch


ROOT = Path(__file__).resolve().parents[1]


def accepted_match(champion_id: str) -> ChampionMatch:
    return ChampionMatch(
        champion_id,
        0.95,
        0.30,
        0.65,
        True,
        champion_id,
        True,
        False,
        24,
        0.95,
    )


def draft_frame(path: str, champion_ids: list[str]) -> DraftFrameResult:
    matches = [accepted_match(champion_id) for champion_id in champion_ids]
    return DraftFrameResult(
        path,
        {"left": tuple(matches[:5]), "right": tuple(matches[5:10])},
        {"left": tuple(matches[10:15]), "right": tuple(matches[15:20])},
        "ok",
    )


def test_versioned_kespa_draft_layout_uses_role_order():
    layout = load_draft_layout(ROOT / "configs/vision/kespa_2026_draft_1920x1080.json")

    assert layout.cdragon_version == "16.14"
    assert [region.x for region in layout.picks["left"]] == [632, 474, 316, 158, 0]
    assert [region.x for region in layout.picks["right"]] == [1130, 1288, 1446, 1604, 1762]


def test_cdragon_art_stores_load_separate_exact_asset_kinds(tmp_path):
    cache = tmp_path / "16.14"
    cache.mkdir()
    (cache / "champion-summary.json").write_text(
        json.dumps([{"id": 1, "alias": "Annie", "name": "Annie"}]),
        encoding="utf-8",
    )
    for directory in (cache / "centered", cache / "tile"):
        directory.mkdir()
        (directory / "Annie.jpg").write_bytes(b"image")

    splash = CDragonChampionSplashStore(version="16.14", cache_root=tmp_path).load()
    tile = CDragonChampionTileStore(version="16.14", cache_root=tmp_path).load()

    assert splash[0].path == cache / "centered" / "Annie.jpg"
    assert tile[0].path == cache / "tile" / "Annie.jpg"


def test_draft_matcher_handles_per_slot_mirroring_and_identity_margin(tmp_path):
    rng = np.random.default_rng(20260721)
    paths = []
    images = []
    for index in range(2):
        image = rng.integers(0, 256, size=(360, 640, 3), dtype=np.uint8)
        cv2.circle(image, (180 + index * 220, 170), 70, (20, 220, 80), 8)
        path = tmp_path / f"champion-{index}.jpg"
        cv2.imwrite(str(path), image)
        paths.append(path)
        images.append(image)
    assets = [
        ChampionAsset(f"Champion{index}", str(index), f"Champion {index}", path.name, path)
        for index, path in enumerate(paths)
    ]
    matcher = DraftChampionMatcher(assets)
    query = cv2.flip(images[0][80:300, 100:300], 1)

    result = matcher.match(query)

    assert result.accepted is True
    assert result.champion_id == "Champion0"
    assert result.mirrored is True
    assert result.inlier_count is not None and result.inlier_count >= 8
    assert result.margin >= 0.20


def test_draft_sequence_requires_repeated_unique_accepted_matches():
    champions = [f"Champion{index}" for index in range(20)]
    result = DraftSequenceAggregator().aggregate(
        [draft_frame("one.jpg", champions), draft_frame("two.jpg", champions)]
    )

    assert result.source_status == "ok"
    assert result.picks["left"][0].value == "Champion0"
    assert result.bans["right"][-1].value == "Champion19"


def test_draft_sequence_rejects_duplicate_champions():
    champions = [f"Champion{index}" for index in range(20)]
    champions[-1] = champions[0]
    result = DraftSequenceAggregator().aggregate(
        [draft_frame("one.jpg", champions), draft_frame("two.jpg", champions)]
    )

    assert result.source_status == "partial_low_confidence"
    assert result.picks["left"][0].reason == "duplicate_champion"
    assert result.bans["right"][-1].reason == "duplicate_champion"
