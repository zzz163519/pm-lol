from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_list(cls, value: list[int]) -> "Region":
        if len(value) != 4:
            raise ValueError("region must contain [x, y, width, height]")
        region = cls(*map(int, value))
        if min(region.x, region.y) < 0 or region.width < 1 or region.height < 1:
            raise ValueError(f"invalid region: {value}")
        return region

    def scale(self, source_width: int, source_height: int, target_width: int, target_height: int) -> "Region":
        if min(source_width, source_height, target_width, target_height) < 1:
            raise ValueError("frame dimensions must be positive")
        sx = target_width / source_width
        sy = target_height / source_height
        return Region(
            x=round(self.x * sx),
            y=round(self.y * sy),
            width=max(1, round(self.width * sx)),
            height=max(1, round(self.height * sy)),
        )

    def bounds(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.width, self.y + self.height


@dataclass(frozen=True, slots=True)
class BroadcastLayout:
    layout_id: str
    schema_version: int
    reference_width: int
    reference_height: int
    ddragon_version: str
    live_indicator: Region
    scoreboard: Region
    picks: dict[str, tuple[Region, ...]]
    bans: dict[str, tuple[Region, ...]]
    fields: dict[str, Region]
    thresholds: dict[str, float]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BroadcastLayout":
        reference = payload.get("referenceResolution", {})
        layout = cls(
            layout_id=str(payload["layoutId"]),
            schema_version=int(payload.get("schemaVersion", 1)),
            reference_width=int(reference["width"]),
            reference_height=int(reference["height"]),
            ddragon_version=str(payload["ddragonVersion"]),
            live_indicator=Region.from_list(payload["regions"]["liveIndicator"]),
            scoreboard=Region.from_list(payload["regions"]["scoreboard"]),
            picks={
                side: tuple(Region.from_list(region) for region in regions)
                for side, regions in payload["regions"]["picks"].items()
            },
            bans={
                side: tuple(Region.from_list(region) for region in regions)
                for side, regions in payload["regions"]["bans"].items()
            },
            fields={name: Region.from_list(region) for name, region in payload["regions"]["fields"].items()},
            thresholds={name: float(value) for name, value in payload.get("thresholds", {}).items()},
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported layout schema version: {self.schema_version}")
        if min(self.reference_width, self.reference_height) < 1:
            raise ValueError("reference resolution must be positive")
        for side in ("left", "right"):
            if len(self.picks.get(side, ())) != 5:
                raise ValueError(f"{side} must define five pick regions")
            if len(self.bans.get(side, ())) != 5:
                raise ValueError(f"{side} must define five ban regions")
        required_fields = {
            "clock",
            "leftGold",
            "rightGold",
            "leftKills",
            "rightKills",
            "leftTowers",
            "rightTowers",
            "leftDragons",
            "rightDragons",
        }
        missing = required_fields.difference(self.fields)
        if missing:
            raise ValueError(f"missing required field regions: {sorted(missing)}")

    def scaled_region(self, region: Region, frame_width: int, frame_height: int) -> Region:
        return region.scale(self.reference_width, self.reference_height, frame_width, frame_height)


def load_layout(path: Path | str) -> BroadcastLayout:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return BroadcastLayout.from_dict(payload)
