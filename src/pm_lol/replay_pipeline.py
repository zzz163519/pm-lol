from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pm_lol.collectors.polymarket_quote_recorder import QuoteTarget, PolymarketQuoteRecorder
from pm_lol.models import CollectorRunEvent, Game, Market, Match
from pm_lol.resolvers.market_match_resolver import resolve_market_to_game, team_name_confidence
from pm_lol.sources.lolesports import parse_event_details, parse_window
from pm_lol.sources.polymarket import parse_market
from pm_lol.storage import SCHEMA_VERSION, SQLiteStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SPIKE_DIR = PROJECT_ROOT / "docs" / "source-spike"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "replay.db"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "reports" / "replay-report.md"


def run_replay(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    storage = SQLiteStorage(db_path)
    report_path = Path(report_path) if report_path is not None else _default_report_path(db_path)

    match, games = parse_event_details(_load_json("lolesports-event-t1-gen-sample.json"))
    drafts, game_state = parse_window(_load_json("lolesports-window-t1-gen-g1-15m-sample.json"))
    market = parse_market(_load_json("polymarket-market-sample.json"))

    storage.upsert_match(match)
    for game in games:
        storage.upsert_game(game)
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:lolesports_event_details",
            collector_name="replay_pipeline",
            source="lolesports_event_details",
            target=match.match_id,
            source_status="ok",
            outcome="match_games_written",
            records_read=1,
            records_written=1 + len(games),
        )
    )

    game_for_window = next(game for game in games if game.game_id == game_state.game_id)
    storage.insert_game_state_snapshot(game_state)
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:lolesports_window",
            collector_name="replay_pipeline",
            source="lolesports_livestats_window",
            target=game_state.game_id,
            source_status=game_state.source_status,
            outcome="game_state_written",
            records_read=1,
            records_written=1,
        )
    )

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
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:polymarket_market",
            collector_name="replay_pipeline",
            source="polymarket_gamma",
            target=market.slug,
            source_status="ok",
            outcome="market_written",
            records_read=1,
            records_written=1,
        )
    )
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
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:polymarket_quotes",
            collector_name="polymarket_quote_recorder",
            source="polymarket_clob_rest",
            target=market.slug,
            source_status="ok",
            outcome="quotes_written",
            records_read=len(quote_targets),
            records_written=quote_summary["quotes_written"],
        )
    )

    resolved = resolve_market_to_game(market, match, games)
    game_number = _extract_game_number(market) or games[0].game_number
    resolver_game = next((game for game in games if game.game_number == game_number), games[0])
    mapping_confidence = (
        resolved.mapping_confidence if resolved else _market_match_confidence(market, match)
    )
    resolver_status = "ok" if resolved else "skipped_low_confidence"
    storage.insert_resolved_market_attempt(
        market=market,
        match=match,
        game=resolver_game,
        mapping_confidence=mapping_confidence,
        market_status=resolved.market_status if resolved else "skipped_low_confidence",
        skip_reason=None if resolved else "mapping_confidence_below_0.90",
    )
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:market_resolver",
            collector_name="market_match_resolver",
            source="market_match_resolver",
            target=market.slug,
            source_status=resolver_status,
            outcome="mapped" if resolved else "skipped",
            records_read=1,
            records_written=1,
            error_code=None if resolved else "mapping_confidence_below_0.90",
        )
    )
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:cito_stale",
            collector_name="live_game_state_connector",
            source="cito_visual_state",
            target=game_state.game_id,
            source_status="stale",
            outcome="observed_fixture_status",
            records_read=1,
            records_written=0,
            budget_state={"remaining": 2},
        )
    )
    storage.record_collector_run_event(
        CollectorRunEvent(
            run_id="replay:cito_rate_limited",
            collector_name="live_game_state_connector",
            source="cito_visual_state",
            target=game_state.game_id,
            source_status="rate_limited",
            outcome="skipped",
            records_read=1,
            records_written=0,
            error_code="http_429",
            budget_state={"backoff_seconds": 60},
        )
    )

    source_status_summary = _source_status_summary(storage.list_collector_run_events())
    _write_report(
        storage=storage,
        report_path=report_path,
        mapping_confidence=mapping_confidence,
        resolved=resolved is not None,
        source_status_summary=source_status_summary,
    )

    return {
        "database": str(Path(db_path)),
        "schema_version": storage.get_schema_version(),
        "report_path": str(report_path),
        "matches": 1,
        "games": len(games),
        "draft_snapshots": len(drafts),
        "game_state_snapshots": 1,
        "markets": 1,
        "quotes": quote_summary["quotes_written"],
        "resolved_markets": 1,
        "mappingConfidence": round(mapping_confidence, 4),
        "resolved": resolved is not None,
        "collector_events": len(storage.list_collector_run_events()),
        "source_status_summary": source_status_summary,
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


def _default_report_path(db_path: Path) -> Path:
    if db_path.resolve() == DEFAULT_DB_PATH.resolve():
        return DEFAULT_REPORT_PATH
    return db_path.with_name(f"{db_path.stem}-report.md")


def _source_status_summary(events: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for event in events:
        status = event["source_status"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def _write_report(
    *,
    storage: SQLiteStorage,
    report_path: Path,
    mapping_confidence: float,
    resolved: bool,
    source_status_summary: dict[str, int],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    quotes = storage.query_quotes()
    games = storage.list_games_for_match("115548128963037587")
    game_state_rows = (
        storage.get_game_state_snapshots(games[0].game_id) if games else []
    )
    events = storage.list_collector_run_events()

    lines = [
        "# PM-LOL Phase 1 Replay Report",
        "",
        f"Schema version: `{SCHEMA_VERSION}`",
        "",
        "Boundary: No fair probability, edge, signal, paper trading, wallet, or order output.",
        "",
        "## Mapping",
        "",
        f"- mappingConfidence: `{mapping_confidence:.4f}`",
        f"- resolved: `{str(resolved).lower()}`",
        "",
        "## Quote timeline",
        "",
    ]
    lines.extend(
        f"- `{row['observed_at']}` market `{row['market_slug']}` outcome `{row['outcome']}` "
        f"bid `{row['best_bid']}` ask `{row['best_ask']}` status `{row['source_status']}`"
        for row in quotes
    )
    lines.extend(["", "## Game state timeline", ""])
    lines.extend(
        f"- `{row.timestamp}` game `{row.game_id}` state `{row.game_state}` "
        f"clock `{row.game_clock}` gold `{row.blue_gold}-{row.red_gold}` "
        f"status `{row.source_status}`"
        for row in game_state_rows
    )
    lines.extend(["", "## Source status timeline", ""])
    lines.extend(
        f"- `{event['observed_at']}` `{event['source']}` target `{event['target']}` "
        f"outcome `{event['outcome']}` status `{event['source_status']}` "
        f"error `{event['error_code']}` budget `{event['budget_state']}`"
        for event in events
    )
    lines.extend(["", "## Source status summary", ""])
    lines.extend(
        f"- `{status}`: `{count}`"
        for status, count in sorted(source_status_summary.items())
    )
    lines.append("")
    report_path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
