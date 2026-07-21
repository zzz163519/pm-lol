from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OcrReading:
    raw_text: str | None
    value: int | float | str | None
    confidence: float
    accepted: bool


class RecognitionEngine(Protocol):
    def __call__(self, image: Any, **kwargs: Any) -> tuple[Any, Any]: ...


class RapidOcrAdapter:
    def __init__(self, engine: RecognitionEngine | None = None, *, min_confidence: float = 0.70) -> None:
        if engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:  # pragma: no cover - optional runtime dependency
                raise RuntimeError("RapidOCR is missing; install pm-lol[vision-spike]") from exc
            engine = RapidOCR()
        self.engine = engine
        self.min_confidence = min_confidence

    def read(self, image: Any, kind: str) -> OcrReading:
        candidates: list[tuple[str, float]] = []
        for variant in self._variants(image):
            result, _ = self.engine(variant, use_det=False, use_cls=False, use_rec=True)
            candidates.extend(_recognition_candidates(result))
        parsed = [(*_parse_value(text, kind), confidence) for text, confidence in candidates]
        valid = [(raw, value, confidence) for raw, value, confidence in parsed if value is not None]
        if not valid:
            best_raw, best_confidence = max(candidates, key=lambda item: item[1], default=(None, 0.0))
            return OcrReading(best_raw, None, best_confidence, False)
        raw, value, confidence = max(valid, key=lambda item: item[2])
        return OcrReading(raw, value, confidence, confidence >= self.min_confidence)

    @staticmethod
    def _variants(image: Any) -> list[Any]:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OpenCV is missing; install pm-lol[vision-spike]") from exc
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        upscaled = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        _, threshold = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return [image, upscaled, threshold]


def _recognition_candidates(result: Any) -> list[tuple[str, float]]:
    if not result:
        return []
    candidates: list[tuple[str, float]] = []
    for item in result:
        if len(item) == 2 and isinstance(item[0], str):
            candidates.append((item[0], float(item[1])))
        elif len(item) >= 3 and isinstance(item[1], str):
            candidates.append((item[1], float(item[2])))
    return candidates


def _parse_value(text: str, kind: str) -> tuple[str, int | float | str | None]:
    compact = re.sub(r"\s+", "", text).upper()
    if kind == "clock":
        match = re.search(r"(\d{1,2})[:.;](\d{2})", compact)
        if not match:
            return text, None
        minutes, seconds = map(int, match.groups())
        return text, minutes * 60 + seconds if seconds < 60 else None
    if kind == "gold":
        normalized = compact.replace("O", "0").replace(",", ".")
        match = re.search(r"(\d{1,3}(?:\.\d)?)K", normalized)
        if not match:
            return text, None
        return text, round(float(match.group(1)) * 1000)
    if kind == "integer":
        normalized = compact.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"}))
        match = re.search(r"\d{1,2}", normalized)
        return text, int(match.group()) if match else None
    if kind == "text":
        return text, compact or None
    raise ValueError(f"unsupported OCR kind: {kind}")
