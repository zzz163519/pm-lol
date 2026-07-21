from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .ddragon import ChampionAsset


@dataclass(frozen=True, slots=True)
class ChampionMatch:
    champion_id: str | None
    score: float
    runner_up_score: float
    margin: float
    accepted: bool
    candidate_id: str | None = None
    geometrically_verified: bool = False


@dataclass(frozen=True, slots=True)
class _ImageFeatures:
    gray: Any
    edges: Any
    histogram: Any
    keypoints: Any
    descriptors: Any


class ChampionMatcher:
    def __init__(
        self,
        assets: Iterable[ChampionAsset],
        *,
        min_score: float = 0.55,
        min_margin: float = 0.05,
        size: int = 64,
    ) -> None:
        cv2, np = _vision_modules()
        self.cv2 = cv2
        self.np = np
        self.min_score = min_score
        self.min_margin = min_margin
        self.size = size
        self.sift = cv2.SIFT_create(contrastThreshold=0.02)
        self.local_matcher = cv2.BFMatcher()
        self.templates: dict[str, Any] = {}
        for asset in assets:
            image = cv2.imread(str(Path(asset.path)), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"unable to read champion template: {asset.path}")
            self.templates[asset.champion_id] = self._features(image)
        if not self.templates:
            raise ValueError("at least one champion template is required")

    def match(self, image: Any) -> ChampionMatch:
        query = self._features(image)
        scored = sorted(
            (
                (*self._score(query, template), champion_id)
                for champion_id, template in self.templates.items()
            ),
            key=lambda candidate: (candidate[1], candidate[0]),
            reverse=True,
        )
        best_score, geometrically_verified, best_id = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - runner_up
        accepted = geometrically_verified and best_score >= self.min_score and margin >= self.min_margin
        return ChampionMatch(
            best_id if accepted else None,
            best_score,
            runner_up,
            margin,
            accepted,
            best_id,
            geometrically_verified,
        )

    def _features(self, image: Any) -> _ImageFeatures:
        cv2 = self.cv2
        resized = cv2.resize(image, (self.size, self.size), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray).astype("float32") / 255.0
        edges = cv2.Canny((gray * 255).astype("uint8"), 60, 160).astype("float32") / 255.0
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        local_image = cv2.resize(image, (128, 128), interpolation=cv2.INTER_CUBIC)
        local_gray = cv2.cvtColor(local_image, cv2.COLOR_BGR2GRAY)
        keypoints, descriptors = self.sift.detectAndCompute(local_gray, None)
        return _ImageFeatures(gray, edges, hist, keypoints, descriptors)

    def _score(self, query: _ImageFeatures, template: _ImageFeatures) -> tuple[float, bool]:
        cv2 = self.cv2
        gray_score = float(cv2.matchTemplate(query.gray, template.gray, cv2.TM_CCOEFF_NORMED)[0, 0])
        edge_score = float(cv2.matchTemplate(query.edges, template.edges, cv2.TM_CCOEFF_NORMED)[0, 0])
        hist_score = float(cv2.compareHist(query.histogram, template.histogram, cv2.HISTCMP_CORREL))
        normalized_gray = max(0.0, min(1.0, (gray_score + 1.0) / 2.0))
        normalized_edge = max(0.0, min(1.0, (edge_score + 1.0) / 2.0))
        normalized_hist = max(0.0, min(1.0, (hist_score + 1.0) / 2.0))
        global_score = 0.55 * normalized_gray + 0.30 * normalized_edge + 0.15 * normalized_hist
        local_score, geometrically_verified = self._local_score(query, template)
        if not geometrically_verified:
            return global_score * 0.50, False
        return 0.90 * local_score + 0.10 * global_score, True

    def _local_score(self, query: _ImageFeatures, template: _ImageFeatures) -> tuple[float, bool]:
        if query.descriptors is None or template.descriptors is None or len(template.descriptors) < 2:
            return 0.0, False
        pairs = self.local_matcher.knnMatch(query.descriptors, template.descriptors, k=2)
        good = [
            pair[0]
            for pair in pairs
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance
        ]
        if len(good) < 4:
            return 0.0, False

        query_points = self.np.float32([query.keypoints[match.queryIdx].pt for match in good]).reshape(-1, 1, 2)
        template_points = self.np.float32(
            [template.keypoints[match.trainIdx].pt for match in good]
        ).reshape(-1, 1, 2)
        try:
            _, mask = self.cv2.findHomography(template_points, query_points, self.cv2.RANSAC, 5.0)
        except self.cv2.error:
            return 0.0, False
        if mask is None:
            return 0.0, False
        inlier_matches = [match for match, is_inlier in zip(good, mask.ravel()) if is_inlier]
        if len(inlier_matches) < 4:
            return 0.0, False

        count_score = min(1.0, len(inlier_matches) / 6.0)
        inlier_ratio = len(inlier_matches) / len(good)
        quality_score = sum(
            max(0.0, 1.0 - match.distance / 512.0) for match in inlier_matches
        ) / len(inlier_matches)
        return 0.40 * count_score + 0.35 * inlier_ratio + 0.25 * quality_score, True


def _vision_modules() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on optional runtime extras
        raise RuntimeError("vision dependencies are missing; install pm-lol[vision-spike]") from exc
    return cv2, np
