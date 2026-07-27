from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar


T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True, slots=True)
class ConsensusValue(Generic[T]):
    value: T | None
    agreement: float
    sample_count: int
    accepted: bool


class TemporalConsensus(Generic[T]):
    def __init__(self, *, window_size: int = 3, min_samples: int = 2, min_agreement: float = 2 / 3) -> None:
        if window_size < 1 or min_samples < 1 or min_samples > window_size:
            raise ValueError("invalid consensus sample configuration")
        if not 0 < min_agreement <= 1:
            raise ValueError("min_agreement must be in (0, 1]")
        self.values: deque[T] = deque(maxlen=window_size)
        self.min_samples = min_samples
        self.min_agreement = min_agreement

    def add(self, value: T | None) -> ConsensusValue[T]:
        if value is not None:
            self.values.append(value)
        return self.current()

    def current(self) -> ConsensusValue[T]:
        if not self.values:
            return ConsensusValue(None, 0.0, 0, False)
        value, count = Counter(self.values).most_common(1)[0]
        agreement = count / len(self.values)
        accepted = len(self.values) >= self.min_samples and agreement >= self.min_agreement
        return ConsensusValue(value if accepted else None, agreement, len(self.values), accepted)
