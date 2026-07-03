from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    db_path: Path = Path("data/db/pm_lol.sqlite3")
    resolver_min_confidence: float = 0.9


DEFAULT_SETTINGS = Settings()

MARKET_COLLECTOR_INTERVAL_SEC = 60
QUOTE_RECORDER_INTERVAL_SEC = 15
SCHEDULE_COLLECTOR_INTERVAL_SEC = 300
LIVE_GAME_POLL_INTERVAL_SEC = 10
