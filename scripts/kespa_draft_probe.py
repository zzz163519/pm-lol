#!/usr/bin/env python3
"""Sync exact draft art and extract KeSPA picks/bans without an LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pm_lol.vision.cdragon import CDragonChampionSplashStore, CDragonChampionTileStore
from pm_lol.vision.draft import (
    DraftChampionMatcher,
    DraftExtractor,
    DraftSequenceAggregator,
    load_draft_layout,
)


DEFAULT_LAYOUT = Path("configs/vision/kespa_2026_draft_1920x1080.json")
DEFAULT_CACHE = Path(".cache/pm-lol-vision/cdragon")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "sync-templates", help="Download version-pinned centered splash and tile art."
    )
    extract = subparsers.add_parser("extract", help="Extract one complete draft frame.")
    extract.add_argument("frame", type=Path)
    extract.add_argument("--output", type=Path)
    sequence = subparsers.add_parser(
        "extract-sequence", help="Extract ordered draft frames with strict consensus."
    )
    sequence.add_argument("frames", nargs="+", type=Path)
    sequence.add_argument("--output", type=Path)
    return parser


def build_extractor(layout_path: Path, cache_dir: Path) -> tuple[DraftExtractor, str]:
    layout = load_draft_layout(layout_path)
    splash_assets = CDragonChampionSplashStore(
        version=layout.cdragon_version, cache_root=cache_dir
    ).load()
    tile_assets = CDragonChampionTileStore(
        version=layout.cdragon_version, cache_root=cache_dir
    ).load()
    pick_matcher = DraftChampionMatcher(splash_assets)
    ban_matcher = DraftChampionMatcher(
        tile_assets,
        min_score=0.65,
        min_margin=0.20,
        min_inliers=6,
        min_inlier_ratio=0.75,
        full_score_inliers=8,
        template_width=380,
    )
    return DraftExtractor(pick_matcher, layout, ban_matcher=ban_matcher), layout.cdragon_version


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    layout = load_draft_layout(args.layout)
    splash_store = CDragonChampionSplashStore(
        version=layout.cdragon_version, cache_root=args.cache_dir
    )
    tile_store = CDragonChampionTileStore(
        version=layout.cdragon_version, cache_root=args.cache_dir
    )
    if args.command == "sync-templates":
        splash_assets = splash_store.sync()
        tile_assets = tile_store.sync()
        print(
            json.dumps(
                {
                    "version": layout.cdragon_version,
                    "centeredSplashCount": len(splash_assets),
                    "tileCount": len(tile_assets),
                    "cacheDir": str(splash_store.cache_dir),
                }
            )
        )
        return 0

    extractor, _ = build_extractor(args.layout, args.cache_dir)
    if args.command == "extract":
        result = extractor.extract(args.frame)
        output = result.as_dict()
        source_status = result.source_status
    else:
        frames = [extractor.extract(path) for path in args.frames]
        aggregate = DraftSequenceAggregator().aggregate(frames)
        output = {
            "aggregate": aggregate.as_dict(),
            "frames": [frame.as_dict() for frame in frames],
        }
        source_status = aggregate.source_status
    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if source_status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
