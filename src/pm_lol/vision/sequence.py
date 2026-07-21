from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from .extractor import VisualFrameResult


@dataclass(frozen=True, slots=True)
class SequenceValue:
    value: int | str | None
    confidence: float
    support: int
    sample_count: int
    accepted: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VisualSequenceResult:
    frame_count: int
    retained_frame_count: int
    skipped_frames: tuple[dict[str, str], ...]
    fields: dict[str, SequenceValue]
    picks: dict[str, tuple[SequenceValue, ...]]
    bans: dict[str, tuple[SequenceValue, ...]]
    source_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisualSequenceAggregator:
    """Turn ordered frame extractions into a conservative normalized state.

    Unknown and contradictory values are skipped. Objective counters require
    repeated cross-frame agreement because their broadcast glyphs are small.
    """

    OBJECTIVE_FIELDS = {"leftTowers", "rightTowers", "leftDragons", "rightDragons"}
    MONOTONIC_FIELDS = {
        "leftGold",
        "rightGold",
        "leftKills",
        "rightKills",
        *OBJECTIVE_FIELDS,
    }

    def __init__(
        self,
        *,
        champion_min_score: float = 0.55,
        champion_min_samples: int = 2,
        champion_min_agreement: float = 2 / 3,
        objective_confidence_floor: float = 0.40,
        objective_min_samples: int = 2,
    ) -> None:
        self.champion_min_score = champion_min_score
        self.champion_min_samples = champion_min_samples
        self.champion_min_agreement = champion_min_agreement
        self.objective_confidence_floor = objective_confidence_floor
        self.objective_min_samples = objective_min_samples

    def aggregate(self, results: Iterable[VisualFrameResult]) -> VisualSequenceResult:
        frames = list(results)
        retained, skipped = self._retain_monotonic_live_frames(frames)
        fields = {
            name: self._field_value(name, retained)
            for name in (
                "clock",
                "leftGold",
                "rightGold",
                "leftKills",
                "rightKills",
                "leftTowers",
                "rightTowers",
                "leftDragons",
                "rightDragons",
            )
        }
        picks = self._champion_groups(retained, "picks")
        bans = self._champion_groups(retained, "bans")
        picks, bans = self._reject_duplicate_champions(picks, bans)
        champion_values = [value for group in (picks, bans) for side in group.values() for value in side]
        source_status = (
            "ok"
            if retained
            and all(value.accepted for value in fields.values())
            and len(champion_values) == 20
            and all(value.accepted for value in champion_values)
            else "partial_low_confidence"
        )
        return VisualSequenceResult(
            frame_count=len(frames),
            retained_frame_count=len(retained),
            skipped_frames=tuple(skipped),
            fields=fields,
            picks=picks,
            bans=bans,
            source_status=source_status,
        )

    def _retain_monotonic_live_frames(
        self, frames: list[VisualFrameResult]
    ) -> tuple[list[VisualFrameResult], list[dict[str, str]]]:
        retained: list[VisualFrameResult] = []
        skipped: list[dict[str, str]] = []
        last_clock: int | None = None
        for frame in frames:
            clock = frame.fields.get("clock")
            if not frame.screen_state.startswith("live_gameplay") or clock is None or not clock.accepted:
                skipped.append({"framePath": frame.frame_path, "reason": "not_live_or_clock_unknown"})
                continue
            value = int(clock.value) if isinstance(clock.value, (int, float)) else None
            if value is None or (last_clock is not None and value <= last_clock):
                skipped.append({"framePath": frame.frame_path, "reason": "clock_not_advancing"})
                continue
            retained.append(frame)
            last_clock = value
        return retained, skipped

    def _field_value(self, name: str, frames: list[VisualFrameResult]) -> SequenceValue:
        candidates: list[tuple[int, float]] = []
        previous: int | None = None
        for frame in frames:
            reading = frame.fields.get(name)
            if reading is None or not isinstance(reading.value, (int, float)):
                continue
            value = int(reading.value)
            usable = reading.accepted or (
                name in self.OBJECTIVE_FIELDS and reading.confidence >= self.objective_confidence_floor
            )
            if not usable:
                continue
            if name in self.MONOTONIC_FIELDS and previous is not None and value < previous:
                continue
            candidates.append((value, reading.confidence))
            previous = value
        if not candidates:
            return SequenceValue(None, 0.0, 0, 0, False, "no_usable_samples")
        if name not in self.OBJECTIVE_FIELDS:
            value, confidence = candidates[-1]
            return SequenceValue(value, confidence, 1, len(candidates), True)

        counts = Counter(value for value, _ in candidates)
        accepted_values = [value for value, count in counts.items() if count >= self.objective_min_samples]
        if not accepted_values:
            return SequenceValue(None, 0.0, 0, len(candidates), False, "cross_frame_agreement_required")
        value = max(accepted_values)
        confidences = [confidence for candidate, confidence in candidates if candidate == value]
        return SequenceValue(
            value,
            sum(confidences) / len(confidences),
            len(confidences),
            len(candidates),
            True,
        )

    def _champion_groups(
        self, frames: list[VisualFrameResult], attribute: str
    ) -> dict[str, tuple[SequenceValue, ...]]:
        result: dict[str, tuple[SequenceValue, ...]] = {}
        for side in ("left", "right"):
            slot_count = max((len(getattr(frame, attribute).get(side, ())) for frame in frames), default=0)
            slots = []
            for index in range(slot_count):
                candidates: list[tuple[str, float]] = []
                for frame in frames:
                    matches = getattr(frame, attribute).get(side, ())
                    if index >= len(matches):
                        continue
                    match = matches[index]
                    candidate = match.candidate_id or match.champion_id
                    if (
                        candidate is not None
                        and match.geometrically_verified
                        and match.score >= self.champion_min_score
                    ):
                        candidates.append((candidate, match.score))
                slots.append(self._champion_consensus(candidates))
            result[side] = tuple(slots)
        return result

    def _champion_consensus(self, candidates: list[tuple[str, float]]) -> SequenceValue:
        if not candidates:
            return SequenceValue(None, 0.0, 0, 0, False, "no_geometrically_verified_samples")
        champion, support = Counter(candidate for candidate, _ in candidates).most_common(1)[0]
        agreement = support / len(candidates)
        confidence = sum(score for candidate, score in candidates if candidate == champion) / support
        accepted = support >= self.champion_min_samples and agreement >= self.champion_min_agreement
        return SequenceValue(
            champion if accepted else None,
            confidence,
            support,
            len(candidates),
            accepted,
            None if accepted else "cross_frame_agreement_required",
        )

    @staticmethod
    def _reject_duplicate_champions(
        picks: dict[str, tuple[SequenceValue, ...]],
        bans: dict[str, tuple[SequenceValue, ...]],
    ) -> tuple[dict[str, tuple[SequenceValue, ...]], dict[str, tuple[SequenceValue, ...]]]:
        values = [value.value for group in (picks, bans) for side in group.values() for value in side if value.accepted]
        duplicates = {value for value, count in Counter(values).items() if count > 1}
        if not duplicates:
            return picks, bans

        def reject(group: dict[str, tuple[SequenceValue, ...]]) -> dict[str, tuple[SequenceValue, ...]]:
            return {
                side: tuple(
                    SequenceValue(None, value.confidence, value.support, value.sample_count, False, "duplicate_champion")
                    if value.value in duplicates
                    else value
                    for value in slots
                )
                for side, slots in group.items()
            }

        return reject(picks), reject(bans)


def observation_metrics(
    observations: Iterable[dict[str, Any]], *, expected_interval_sec: float
) -> dict[str, Any]:
    """Summarize capture timing without inventing source-side latency."""
    if expected_interval_sec <= 0:
        raise ValueError("expected_interval_sec must be positive")
    parsed: list[tuple[str, datetime]] = []
    for observation in observations:
        raw = observation.get("observedAt")
        if not isinstance(raw, str):
            continue
        try:
            parsed.append((str(observation.get("path") or ""), datetime.fromisoformat(raw.replace("Z", "+00:00"))))
        except ValueError:
            continue
    gaps = [
        (current_path, (current_time - prior_time).total_seconds())
        for (_, prior_time), (current_path, current_time) in zip(parsed, parsed[1:])
    ]
    interruptions = [
        {"framePath": path, "gapSec": gap}
        for path, gap in gaps
        if gap > expected_interval_sec * 2.5
    ]
    return {
        "observedFrameCount": len(parsed),
        "firstObservedAt": parsed[0][1].isoformat().replace("+00:00", "Z") if parsed else None,
        "lastObservedAt": parsed[-1][1].isoformat().replace("+00:00", "Z") if parsed else None,
        "maxObservationGapSec": max((gap for _, gap in gaps), default=None),
        "interruptions": interruptions,
        "sourceLatencySec": None,
        "sourceLatencyStatus": "not_measured_without_authoritative_source_timestamp",
    }
