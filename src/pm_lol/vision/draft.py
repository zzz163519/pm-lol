from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .ddragon import ChampionAsset
from .layout import Region
from .matcher import ChampionMatch, _vision_modules
from .sequence import SequenceValue


@dataclass(frozen=True, slots=True)
class DraftLayout:
    layout_id: str
    schema_version: int
    reference_width: int
    reference_height: int
    cdragon_version: str
    picks: dict[str, tuple[Region, ...]]
    bans: dict[str, tuple[Region, ...]]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DraftLayout":
        reference = payload.get("referenceResolution", {})
        regions = payload.get("regions", {})
        layout = cls(
            layout_id=str(payload["layoutId"]),
            schema_version=int(payload.get("schemaVersion", 1)),
            reference_width=int(reference["width"]),
            reference_height=int(reference["height"]),
            cdragon_version=str(payload["cdragonVersion"]),
            picks={
                side: tuple(Region.from_list(region) for region in values)
                for side, values in regions["picks"].items()
            },
            bans={
                side: tuple(Region.from_list(region) for region in values)
                for side, values in regions["bans"].items()
            },
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported draft layout schema version: {self.schema_version}")
        if min(self.reference_width, self.reference_height) < 1:
            raise ValueError("draft reference resolution must be positive")
        for side in ("left", "right"):
            if len(self.picks.get(side, ())) != 5:
                raise ValueError(f"{side} must define five draft pick regions")
            if len(self.bans.get(side, ())) != 5:
                raise ValueError(f"{side} must define five draft ban regions")

    def scaled_region(self, region: Region, frame_width: int, frame_height: int) -> Region:
        return region.scale(self.reference_width, self.reference_height, frame_width, frame_height)


def load_draft_layout(path: Path | str) -> DraftLayout:
    return DraftLayout.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class DraftFrameResult:
    frame_path: str
    picks: dict[str, tuple[ChampionMatch, ...]]
    bans: dict[str, tuple[ChampionMatch, ...]]
    source_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DraftSequenceResult:
    frame_count: int
    picks: dict[str, tuple[SequenceValue, ...]]
    bans: dict[str, tuple[SequenceValue, ...]]
    source_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DraftSequenceAggregator:
    """Require repeated accepted exact-art matches for every draft slot."""

    def __init__(
        self, *, min_samples: int = 2, min_agreement: float = 2 / 3
    ) -> None:
        if min_samples < 1:
            raise ValueError("min_samples must be positive")
        if not 0 < min_agreement <= 1:
            raise ValueError("min_agreement must be in (0, 1]")
        self.min_samples = min_samples
        self.min_agreement = min_agreement

    def aggregate(self, results: Iterable[DraftFrameResult]) -> DraftSequenceResult:
        frames = list(results)
        picks = self._groups(frames, "picks")
        bans = self._groups(frames, "bans")
        values = [
            value
            for group in (picks, bans)
            for slots in group.values()
            for value in slots
        ]
        accepted = [value.value for value in values if value.accepted]
        duplicates = {value for value, count in Counter(accepted).items() if count > 1}
        if duplicates:
            picks = self._reject_duplicates(picks, duplicates)
            bans = self._reject_duplicates(bans, duplicates)
            values = [
                value
                for group in (picks, bans)
                for slots in group.values()
                for value in slots
            ]
        source_status = (
            "ok"
            if len(values) == 20 and all(value.accepted for value in values)
            else "partial_low_confidence"
        )
        return DraftSequenceResult(len(frames), picks, bans, source_status)

    def _groups(
        self, frames: list[DraftFrameResult], attribute: str
    ) -> dict[str, tuple[SequenceValue, ...]]:
        result: dict[str, tuple[SequenceValue, ...]] = {}
        for side in ("left", "right"):
            slots = []
            for index in range(5):
                candidates = []
                for frame in frames:
                    matches = getattr(frame, attribute).get(side, ())
                    if index >= len(matches):
                        continue
                    match = matches[index]
                    if match.accepted and match.champion_id is not None:
                        candidates.append((match.champion_id, match.score))
                slots.append(self._consensus(candidates))
            result[side] = tuple(slots)
        return result

    def _consensus(self, candidates: list[tuple[str, float]]) -> SequenceValue:
        if not candidates:
            return SequenceValue(None, 0.0, 0, 0, False, "no_accepted_samples")
        champion, support = Counter(value for value, _ in candidates).most_common(1)[0]
        agreement = support / len(candidates)
        confidence = sum(score for value, score in candidates if value == champion) / support
        accepted = support >= self.min_samples and agreement >= self.min_agreement
        return SequenceValue(
            champion if accepted else None,
            confidence,
            support,
            len(candidates),
            accepted,
            None if accepted else "cross_frame_agreement_required",
            None if accepted else champion,
        )

    @staticmethod
    def _reject_duplicates(
        groups: dict[str, tuple[SequenceValue, ...]], duplicates: set[int | str | None]
    ) -> dict[str, tuple[SequenceValue, ...]]:
        return {
            side: tuple(
                SequenceValue(
                    None,
                    value.confidence,
                    value.support,
                    value.sample_count,
                    False,
                    "duplicate_champion",
                    str(value.value) if value.value is not None else None,
                )
                if value.value in duplicates
                else value
                for value in slots
            )
            for side, slots in groups.items()
        }


@dataclass(frozen=True, slots=True)
class _LocalFeatures:
    keypoints: Any
    descriptors: Any


class DraftChampionMatcher:
    """Match large draft portraits against exact centered splash artwork.

    Draft graphics can crop and mirror each portrait independently. SIFT is
    used only on these large, exact-art draft panels; acceptance requires a
    strong homography inlier count, ratio, and identity margin.
    """

    def __init__(
        self,
        assets: Iterable[ChampionAsset],
        *,
        min_score: float = 0.65,
        min_margin: float = 0.20,
        min_inliers: int = 8,
        min_inlier_ratio: float = 0.75,
        full_score_inliers: int = 12,
        template_width: int = 640,
        ratio_test: float = 0.70,
    ) -> None:
        cv2, np = _vision_modules()
        self.cv2 = cv2
        self.np = np
        self.min_score = min_score
        self.min_margin = min_margin
        self.min_inliers = min_inliers
        self.min_inlier_ratio = min_inlier_ratio
        if full_score_inliers < 1:
            raise ValueError("full_score_inliers must be positive")
        self.full_score_inliers = full_score_inliers
        self.template_width = template_width
        self.ratio_test = ratio_test
        self.sift = cv2.SIFT_create(contrastThreshold=0.015)
        self.local_matcher = cv2.BFMatcher()
        self.templates: dict[str, _LocalFeatures] = {}
        for asset in assets:
            image = cv2.imread(str(asset.path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError(f"unable to read draft splash template: {asset.path}")
            height = round(image.shape[0] * template_width / image.shape[1])
            resized = cv2.resize(image, (template_width, height), interpolation=cv2.INTER_AREA)
            self.templates[asset.champion_id] = self._features(resized)
        if not self.templates:
            raise ValueError("at least one draft champion template is required")

    def match(self, image: Any) -> ChampionMatch:
        if image is None or image.size == 0:
            raise ValueError("draft query image must not be empty")
        queries = {
            False: self._features(self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)),
            True: self._features(
                self.cv2.cvtColor(self.cv2.flip(image, 1), self.cv2.COLOR_BGR2GRAY)
            ),
        }
        scored: list[tuple[float, str, bool, int, float]] = []
        for champion_id, template in self.templates.items():
            orientations = [
                (*self._score(query, template), mirrored)
                for mirrored, query in queries.items()
            ]
            score, inliers, inlier_ratio, mirrored = max(orientations)
            scored.append((score, champion_id, mirrored, inliers, inlier_ratio))
        scored.sort(reverse=True)
        score, champion_id, mirrored, inliers, inlier_ratio = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        margin = score - runner_up
        geometrically_verified = (
            inliers >= self.min_inliers and inlier_ratio >= self.min_inlier_ratio
        )
        accepted = (
            geometrically_verified
            and score >= self.min_score
            and margin >= self.min_margin
        )
        return ChampionMatch(
            champion_id if accepted else None,
            score,
            runner_up,
            margin,
            accepted,
            champion_id,
            geometrically_verified,
            mirrored,
            inliers,
            inlier_ratio,
        )

    def _features(self, gray: Any) -> _LocalFeatures:
        keypoints, descriptors = self.sift.detectAndCompute(gray, None)
        return _LocalFeatures(keypoints, descriptors)

    def _score(
        self, query: _LocalFeatures, template: _LocalFeatures
    ) -> tuple[float, int, float]:
        if query.descriptors is None or template.descriptors is None:
            return 0.0, 0, 0.0
        pairs = self.local_matcher.knnMatch(query.descriptors, template.descriptors, k=2)
        good = [
            pair[0]
            for pair in pairs
            if len(pair) == 2 and pair[0].distance < self.ratio_test * pair[1].distance
        ]
        if len(good) < 4:
            return 0.0, 0, 0.0
        query_points = self.np.float32(
            [query.keypoints[match.queryIdx].pt for match in good]
        ).reshape(-1, 1, 2)
        template_points = self.np.float32(
            [template.keypoints[match.trainIdx].pt for match in good]
        ).reshape(-1, 1, 2)
        try:
            _, mask = self.cv2.findHomography(
                template_points, query_points, self.cv2.RANSAC, 4.0
            )
        except self.cv2.error:
            return 0.0, 0, 0.0
        if mask is None:
            return 0.0, 0, 0.0
        inliers = int(mask.sum())
        inlier_ratio = inliers / len(good)
        score = min(1.0, inliers / self.full_score_inliers) * inlier_ratio
        return score, inliers, inlier_ratio


class DraftExtractor:
    def __init__(
        self,
        matcher: DraftChampionMatcher,
        layout: DraftLayout,
        *,
        ban_matcher: DraftChampionMatcher | None = None,
    ) -> None:
        self.matcher = matcher
        self.ban_matcher = ban_matcher or matcher
        self.layout = layout
        self.cv2 = matcher.cv2

    def extract(self, frame_path: Path | str) -> DraftFrameResult:
        path = Path(frame_path)
        frame = self.cv2.imread(str(path), self.cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"unable to read frame: {path}")
        frame_height, frame_width = frame.shape[:2]
        picks = self._groups(frame, self.layout.picks, frame_width, frame_height)
        bans = self._groups(
            frame,
            self.layout.bans,
            frame_width,
            frame_height,
            matcher=self.ban_matcher,
        )
        matches = [
            match
            for group in (picks, bans)
            for slots in group.values()
            for match in slots
        ]
        accepted_ids = [match.champion_id for match in matches if match.accepted]
        source_status = (
            "ok"
            if len(matches) == 20
            and len(accepted_ids) == 20
            and len(set(accepted_ids)) == 20
            else "partial_low_confidence"
        )
        return DraftFrameResult(str(path), picks, bans, source_status)

    def _groups(
        self,
        frame: Any,
        groups: dict[str, tuple[Region, ...]],
        frame_width: int,
        frame_height: int,
        *,
        matcher: DraftChampionMatcher | None = None,
    ) -> dict[str, tuple[ChampionMatch, ...]]:
        matcher = matcher or self.matcher
        result: dict[str, tuple[ChampionMatch, ...]] = {}
        for side, regions in groups.items():
            matches = []
            for region in regions:
                scaled = self.layout.scaled_region(region, frame_width, frame_height)
                x1, y1, x2, y2 = scaled.bounds()
                matches.append(matcher.match(frame[y1:y2, x1:x2]))
            result[side] = tuple(matches)
        return result
