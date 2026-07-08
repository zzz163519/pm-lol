from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pm_lol.collectors.polymarket_quote_recorder import QuoteTarget, PolymarketQuoteRecorder
from pm_lol.models import Game, Market, Match
from pm_lol.resolvers.market_match_resolver import resolve_market_to_game, team_name_confidence
from pm_lol.sources.lolesports import parse_event_details, parse_window
from pm_lol.sources.polymarket import parse_market
from pm_lol.storage import SQLiteStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SPIKE_DIR = PROJECT_ROOT / "docs" / "source-spike"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "replay.db"


def run_replay(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    storage = SQLiteStorage(db_path)

    match, games = parse_event_details(_load_json("lolesports-event-t1-gen-sample.json"))
    drafts, game_state = parse_window(_load_json("lolesports-window-t1-gen-g1-15m-sample.json"))
    market = parse_market(_load_json("polymarket-market-sample.json"))

    storage.upsert_match(match)
    for game in games:
        storage.upsert_game(game)

    game_for_window = next(game for game in games if game.game_id == game_state.game_id)
    storage.insert_game_state_snapshot(game_state)

    blue_champions = [draft.champion_id for draft in drafts if draft.side == "blue"]
    red_champions = [draft.champion_id for draft in drafts if draft.side == "red"]
    for draft in drafts:
        storage.insert_draft_snapshot(
            draft,
            blue_team_id=game_for_window.blue_team_id,
            red_team_id=game_for_window.red_team_id,
            blue_champions=blue_champions,
            red_champions=red_champions,
        )

    storage.upsert_market(market)
    quote_targets = [
        QuoteTarget(
            event_slug=market.event_slug,
            market_slug=market.slug,
            condition_id=market.condition_id,
            token_id=token_id,
            outcome=outcome,
            game_number=_extract_game_number(market),
        )
        for outcome, token_id in zip(market.outcomes, market.token_ids, strict=False)
    ]
    quote_summary = PolymarketQuoteRecorder(
        _FixtureOrderbookClient(_load_json("polymarket-orderbook-sample.json")),
        storage,
        quote_targets,
    ).run_once()

    resolved = resolve_market_to_game(market, match, games)
    game_number = _extract_game_number(market) or games[0].game_number
    resolver_game = next((game for game in games if game.game_number == game_number), games[0])
    mapping_confidence = (
        resolved.mapping_confidence if resolved else _market_match_confidence(market, match)
    )
    storage.insert_resolved_market_attempt(
        market=market,
        match=match,
        game=resolver_game,
        mapping_confidence=mapping_confidence,
        market_status=resolved.market_status if resolved else "skipped_low_confidence",
        skip_reason=None if resolved else "mapping_confidence_below_0.90",
    )

    return {
        "database": str(Path(db_path)),
        "matches": 1,
        "games": len(games),
        "draft_snapshots": len(drafts),
        "game_state_snapshots": 1,
        "markets": 1,
        "quotes": quote_summary["quotes_written"],
        "resolved_markets": 1,
        "mappingConfidence": round(mapping_confidence, 4),
        "resolved": resolved is not None,
    }


def main() -> None:
    summary = run_replay()
    print(json.dumps(summary, indent=2, sort_keys=True))


def _load_json(filename: str) -> Any:
    return json.loads((SOURCE_SPIKE_DIR / filename).read_text())


class _FixtureOrderbookClient:
    def __init__(self, books: list[dict[str, Any]]) -> None:
        self.books = books

    def get_orderbook(self, token_id: str) -> dict[str, Any]:
        return next(book for book in self.books if book["asset_id"] == token_id)


def _market_match_confidence(market: Market, match: Match) -> float:
    if len(market.outcomes) < 2:
        return 0.0
    direct = (
        team_name_confidence(market.outcomes[0], match.team_a_name)
        + team_name_confidence(market.outcomes[1], match.team_b_name)
    ) / 2
    swapped = (
        team_name_confidence(market.outcomes[0], match.team_b_name)
        + team_name_confidence(market.outcomes[1], match.team_a_name)
    ) / 2
    return max(direct, swapped)


def _extract_game_number(market: Market) -> int | None:
    match = re.search(r"game\s*-?\s*(\d+)", f"{market.slug} {market.title}".lower())
    return int(match.group(1)) if match else None


if __name__ == "__main__":
    main()
