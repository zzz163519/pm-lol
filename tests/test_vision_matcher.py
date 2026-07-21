from pathlib import Path

import cv2
import numpy as np

from pm_lol.vision.ddragon import ChampionAsset
from pm_lol.vision.matcher import ChampionMatcher


def _asset(tmp_path: Path, champion_id: str, image: np.ndarray) -> ChampionAsset:
    path = tmp_path / f"{champion_id}.png"
    assert cv2.imwrite(str(path), image)
    return ChampionAsset(champion_id, champion_id, champion_id, path.name, path)


def test_champion_matcher_accepts_clear_unique_template(tmp_path: Path):
    rng = np.random.default_rng(42)
    red = rng.integers(0, 80, size=(64, 64, 3), dtype=np.uint8)
    red[:, :, 2] = np.maximum(red[:, :, 2], 180)
    cv2.line(red, (5, 5), (58, 58), (255, 255, 255), 5)
    blue = rng.integers(0, 80, size=(64, 64, 3), dtype=np.uint8)
    blue[:, :, 0] = np.maximum(blue[:, :, 0], 180)
    cv2.circle(blue, (32, 32), 20, (255, 255, 255), 4)
    matcher = ChampionMatcher(
        [_asset(tmp_path, "Red", red), _asset(tmp_path, "Blue", blue)],
        min_score=0.6,
        min_margin=0.01,
    )

    result = matcher.match(red)

    assert result.accepted is True
    assert result.champion_id == "Red"
    assert result.score > result.runner_up_score


def test_champion_matcher_rejects_spatially_inconsistent_feature_matches(tmp_path: Path):
    rng = np.random.default_rng(7)
    correct = rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
    for x, y in ((16, 18), (48, 30), (80, 42), (28, 78), (67, 91), (105, 104)):
        cv2.circle(correct, (x, y), 6, (255, 255, 255), 2)
        cv2.line(correct, (x - 5, y), (x + 5, y), (0, 0, 0), 1)

    transform = cv2.getRotationMatrix2D((64, 64), 7, 0.92)
    query = cv2.warpAffine(correct, transform, (128, 128))
    inconsistent = np.zeros_like(correct)
    tiles = [correct[y : y + 32, x : x + 32] for y in (0, 32, 64, 96) for x in (0, 32, 64, 96)]
    rng.shuffle(tiles)
    for tile, (y, x) in zip(tiles, ((y, x) for y in (0, 32, 64, 96) for x in (0, 32, 64, 96))):
        inconsistent[y : y + 32, x : x + 32] = tile

    matcher = ChampionMatcher(
        [
            _asset(tmp_path, "Correct", correct),
            _asset(tmp_path, "Inconsistent", inconsistent),
        ],
        min_score=0.55,
        min_margin=0.01,
    )

    result = matcher.match(query)

    assert result.accepted is True
    assert result.champion_id == "Correct"
