from __future__ import annotations

import re
from difflib import SequenceMatcher

from pm_lol.models import Game, Market, Match, ResolvedMarket
from pm_lol.storage import SQLiteStorage


ALIASES = {
    "kt": "ktrolster",
    "ktc": "ktrolsterchallengers",
    "gen": "geng",
    "geng": "geng",
    "sgw": "saigonwarriors",
    "t1": "t1",
}


def resolve_market_to_game(
    market: Market,
    match: Match,
    games: list[Game],
    min_confidence: float = 0.9,
) -> ResolvedMarket | None:
    if market.market_type != "game_winner":
        return None

    game_number = _extract_game_number(market)
    if game_number is None:
        return None

    game = next((candidate for candidate in games if candidate.game_number == game_number), None)
    if game is None:
        return None

    if len(market.outcomes) < 2:
        return None

    direct = _pair_confidence(
        market.outcomes[0],
        market.outcomes[1],
        match.team_a_name,
        match.team_b_name,
    )
    swapped = _pair_confidence(
        market.outcomes[0],
        market.outcomes[1],
        match.team_b_name,
        match.team_a_name,
    )
    confidence = max(direct, swapped)
    if confidence < min_confidence:
        return None

    return ResolvedMarket(
        market_id=market.market_id,
        condition_id=market.condition_id,
        match_id=match.match_id,
        game_id=game.game_id,
        game_number=game.game_number,
        team_a=match.team_a_name,
        team_b=match.team_b_name,
        blue_team_id=game.blue_team_id,
        red_team_id=game.red_team_id,
        mapping_confidence=confidence,
        market_type=market.market_type,
        market_status="closed" if market.closed else "active",
    )


def resolve_pending_markets(
    storage: SQLiteStorage,
    min_confidence: float = 0.9,
) -> dict[str, int]:
    markets_seen = 0
    resolved_count = 0
    skipped_count = 0
    matches = storage.list_matches()

    for market in storage.list_markets():
        markets_seen += 1
        resolved = None
        for match in matches:
            candidate = resolve_market_to_game(
                market,
                match,
                storage.list_games_for_match(match.match_id),
                min_confidence=min_confidence,
            )
            if candidate is not None:
                resolved = (match, candidate)
                break

        if resolved is None:
            skipped_count += 1
            continue

        match, candidate = resolved
        game = next(
            game
            for game in storage.list_games_for_match(match.match_id)
            if game.game_id == candidate.game_id
        )
        storage.insert_resolved_market_attempt(
            market=market,
            match=match,
            game=game,
            mapping_confidence=candidate.mapping_confidence,
            market_status=candidate.market_status,
            skip_reason=None,
        )
        resolved_count += 1

    return {"markets_seen": markets_seen, "resolved": resolved_count, "skipped": skipped_count}


def team_name_confidence(left: str, right: str) -> float:
    left_norm = _canonical_team_name(left)
    right_norm = _canonical_team_name(right)
    if left_norm == right_norm:
        return 1.0
    if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
        return 0.95
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _pair_confidence(left_a: str, left_b: str, right_a: str, right_b: str) -> float:
    return (team_name_confidence(left_a, right_a) + team_name_confidence(left_b, right_b)) / 2


def _canonical_team_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    normalized = normalized.removesuffix("esports")
    normalized = normalized.removesuffix("gaming")
    return ALIASES.get(normalized, normalized)


def _extract_game_number(market: Market) -> int | None:
    text = f"{market.slug} {market.title}".lower()
    match = re.search(r"game\s*-?\s*(\d+)", text)
    return int(match.group(1)) if match else None
