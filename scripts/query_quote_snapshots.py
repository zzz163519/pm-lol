from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pm_lol.storage import SQLiteStorage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "replay.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Query read-only Polymarket quote snapshots from SQLite.",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--market-slug", help="Filter by Polymarket market slug")
    parser.add_argument("--game-number", type=int, help="Filter by game number")
    parser.add_argument("--token-id", help="Filter by CLOB token id")
    parser.add_argument("--observed-from", help="Inclusive RFC3339 observed_at lower bound")
    parser.add_argument("--observed-to", help="Inclusive RFC3339 observed_at upper bound")
    args = parser.parse_args(argv)

    rows = SQLiteStorage(args.db).query_quotes(
        market_slug=args.market_slug,
        game_number=args.game_number,
        token_id=args.token_id,
        observed_from=args.observed_from,
        observed_to=args.observed_to,
    )
    print(json.dumps({"count": len(rows), "quotes": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
