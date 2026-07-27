"""Pure-code visual extraction primitives for Phase 0 source validation."""

from .layout import BroadcastLayout, Region, load_layout
from .temporal import TemporalConsensus

__all__ = ["BroadcastLayout", "Region", "TemporalConsensus", "load_layout"]
