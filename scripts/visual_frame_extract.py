#!/usr/bin/env python3
"""Sync Riot champion templates and extract KeSPA broadcast frames without an LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pm_lol.vision.ddragon import DDragonChampionStore
from pm_lol.vision.extractor import VisualFrameExtractor
from pm_lol.vision.layout import load_layout
from pm_lol.vision.matcher import ChampionMatcher
from pm_lol.vision.ocr import RapidOcrAdapter
from pm_lol.vision.sequence import VisualSequenceAggregator


DEFAULT_LAYOUT = Path("configs/vision/kespa_2026_1920x1080.json")
DEFAULT_CACHE = Path(".cache/pm-lol-vision/ddragon")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync-templates", help="Download version-pinned Data Dragon champion icons.")
    extract = subparsers.add_parser("extract", help="Extract one saved broadcast frame.")
    extract.add_argument("frame", type=Path)
    extract.add_argument("--output", type=Path)
    extract.add_argument("--skip-live-check", action="store_true")
    sequence = subparsers.add_parser(
        "extract-sequence", help="Extract ordered frames and apply conservative cross-frame agreement."
    )
    sequence.add_argument("frames", nargs="+", type=Path)
    sequence.add_argument("--output", type=Path)
    sequence.add_argument("--skip-live-check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    layout = load_layout(args.layout)
    store = DDragonChampionStore(version=layout.ddragon_version, cache_root=args.cache_dir)
    if args.command == "sync-templates":
        assets = store.sync()
        print(json.dumps({"version": layout.ddragon_version, "count": len(assets), "cacheDir": str(store.cache_dir)}))
        return 0

    assets = store.load()
    matcher = ChampionMatcher(
        assets,
        min_score=layout.thresholds.get("championScore", 0.68),
        min_margin=layout.thresholds.get("championMargin", 0.025),
    )
    ocr = RapidOcrAdapter(min_confidence=layout.thresholds.get("ocrConfidence", 0.70))
    extractor = VisualFrameExtractor(layout=layout, ocr=ocr, champion_matcher=matcher)
    if args.command == "extract":
        result = extractor.extract(args.frame, require_live_indicator=not args.skip_live_check)
        output = result.as_dict()
        source_status = result.source_status
    else:
        frame_results = [
            extractor.extract(frame, require_live_indicator=not args.skip_live_check)
            for frame in args.frames
        ]
        result = VisualSequenceAggregator(
            champion_min_score=layout.thresholds.get("championScore", 0.55)
        ).aggregate(frame_results)
        output = {
            "aggregate": result.as_dict(),
            "frames": [frame.as_dict() for frame in frame_results],
        }
        source_status = result.source_status
    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if source_status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
