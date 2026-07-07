#!/usr/bin/env python3
"""Read-only LoLEsports livestats source smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pm_lol.collectors.lolesports_live_source_smoke import collect_live_source_smoke, lolesports_fetcher


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, help="LoLEsports esportsGameId to probe.")
    parser.add_argument("--output-dir", default="docs/source-spike", help="Directory for raw samples and report.")
    parser.add_argument("--timeout-sec", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = collect_live_source_smoke(
        game_id=args.game_id,
        output_dir=args.output_dir,
        fetcher=lolesports_fetcher(timeout_sec=args.timeout_sec),
    )
    print(
        json.dumps(
            {
                "overallOk": report["overallOk"],
                "gameId": report["gameId"],
                "observedAt": report["observedAt"],
                "fieldCoverage": report["fieldCoverage"],
                "failureReasons": report["failureReasons"],
                "rawSamplePaths": report["rawSamplePaths"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not report["rawSamplePaths"].get("report"):
        return 1
    return 0 if report["overallOk"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
