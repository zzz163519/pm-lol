from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from .layout import BroadcastLayout, Region
from .matcher import ChampionMatch, ChampionMatcher
from .ocr import OcrReading, RapidOcrAdapter


@dataclass(frozen=True, slots=True)
class VisualFrameResult:
    layout_id: str
    frame_path: str
    frame_width: int
    frame_height: int
    screen_state: str
    live_indicator: OcrReading
    fields: dict[str, OcrReading]
    picks: dict[str, tuple[ChampionMatch, ...]]
    bans: dict[str, tuple[ChampionMatch, ...]]
    source_status: str
    overall_confidence: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisualFrameExtractor:
    FIELD_KINDS = {
        "clock": "clock",
        "leftGold": "gold",
        "rightGold": "gold",
        "leftKills": "integer",
        "rightKills": "integer",
        "leftTowers": "integer",
        "rightTowers": "integer",
        "leftDragons": "integer",
        "rightDragons": "integer",
    }

    def __init__(
        self,
        *,
        layout: BroadcastLayout,
        ocr: RapidOcrAdapter,
        champion_matcher: ChampionMatcher | None = None,
    ) -> None:
        self.layout = layout
        self.ocr = ocr
        self.champion_matcher = champion_matcher
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("OpenCV is missing; install pm-lol[vision-spike]") from exc
        self.cv2 = cv2

    def extract(self, frame_path: Path | str, *, require_live_indicator: bool = True) -> VisualFrameResult:
        path = Path(frame_path)
        frame = self.cv2.imread(str(path), self.cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"unable to read frame: {path}")
        frame_height, frame_width = frame.shape[:2]
        live_region = self.layout.scaled_region(self.layout.live_indicator, frame_width, frame_height)
        live_reading = self.ocr.read(_crop(frame, live_region), "text")
        live_text = str(live_reading.value or "")
        fields = {
            name: self.ocr.read(
                _crop(frame, self.layout.scaled_region(region, frame_width, frame_height)),
                self.FIELD_KINDS[name],
            )
            for name, region in self.layout.fields.items()
            if name in self.FIELD_KINDS
        }
        fields = {
            name: _constrain_counter(name, reading)
            for name, reading in fields.items()
        }
        core_scoreboard_fields = ("clock", "leftGold", "rightGold", "leftKills", "rightKills")
        scoreboard_verified = all(
            fields[name].value is not None
            and fields[name].confidence >= (0.60 if name.endswith("Kills") else 0.70)
            for name in core_scoreboard_fields
        )
        if "LIVE" in live_text:
            screen_state = "live_gameplay"
        elif scoreboard_verified:
            screen_state = "live_gameplay_scoreboard_verified"
        else:
            screen_state = "not_live_or_unknown"

        if require_live_indicator and screen_state == "not_live_or_unknown":
            return VisualFrameResult(
                layout_id=self.layout.layout_id,
                frame_path=str(path),
                frame_width=frame_width,
                frame_height=frame_height,
                screen_state=screen_state,
                live_indicator=live_reading,
                fields=fields,
                picks={"left": (), "right": ()},
                bans={"left": (), "right": ()},
                source_status="skipped_not_live_gameplay",
                overall_confidence=live_reading.confidence,
            )

        picks = self._match_regions(frame, self.layout.picks, frame_width, frame_height)
        bans = self._match_regions(frame, self.layout.bans, frame_width, frame_height)
        readings = [reading.confidence for reading in fields.values() if reading.accepted]
        champion_matches = [match for group in (picks, bans) for side in group.values() for match in side]
        readings.extend(match.score for match in champion_matches if match.accepted)
        overall_confidence = sum(readings) / len(readings) if readings else 0.0
        all_fields_accepted = all(fields[name].accepted for name in self.FIELD_KINDS)
        all_champions_accepted = len(champion_matches) == 20 and all(match.accepted for match in champion_matches)
        source_status = "ok" if all_fields_accepted and all_champions_accepted else "partial_low_confidence"
        return VisualFrameResult(
            layout_id=self.layout.layout_id,
            frame_path=str(path),
            frame_width=frame_width,
            frame_height=frame_height,
            screen_state=screen_state,
            live_indicator=live_reading,
            fields=fields,
            picks=picks,
            bans=bans,
            source_status=source_status,
            overall_confidence=overall_confidence,
        )

    def _match_regions(
        self,
        frame: Any,
        regions_by_side: dict[str, tuple[Region, ...]],
        frame_width: int,
        frame_height: int,
    ) -> dict[str, tuple[ChampionMatch, ...]]:
        if self.champion_matcher is None:
            return {side: () for side in regions_by_side}
        result: dict[str, tuple[ChampionMatch, ...]] = {}
        for side, regions in regions_by_side.items():
            matches = []
            for region in regions:
                scaled = self.layout.scaled_region(region, frame_width, frame_height)
                matches.append(self.champion_matcher.match(_crop(frame, scaled)))
            result[side] = tuple(matches)
        return result


def _crop(frame: Any, region: Region) -> Any:
    x1, y1, x2, y2 = region.bounds()
    height, width = frame.shape[:2]
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        raise ValueError(f"region {region} falls outside {width}x{height} frame")
    return frame[y1:y2, x1:x2]


def _constrain_counter(name: str, reading: OcrReading) -> OcrReading:
    maximums = {
        "leftTowers": 11,
        "rightTowers": 11,
        "leftDragons": 6,
        "rightDragons": 6,
    }
    maximum = maximums.get(name)
    if maximum is None or not isinstance(reading.value, int) or reading.value <= maximum:
        return reading
    digits = re.findall(r"\d", reading.raw_text or "")
    if digits and int(digits[0]) <= maximum:
        return OcrReading(reading.raw_text, int(digits[0]), reading.confidence, reading.accepted)
    return OcrReading(reading.raw_text, None, reading.confidence, False)
