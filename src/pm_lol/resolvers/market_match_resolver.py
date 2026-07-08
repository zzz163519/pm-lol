from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from pm_lol.models import Game, Market, MarketResolutionAttempt, Match, ResolvedMarket, TokenTeamMapping
from pm_lol.storage import SQLiteStorage


ALIASES = {
    "bilibili": "blg",
    "bilibiligaming": "blg",
    "blg": "blg",
    "hanwhalife": "hle",
    "hanwhalifeesports": "hle",
    "hle": "hle",
    "kt": "ktrolster",
    "ktc": "ktrolsterchallengers",
    "gen": "geng",
    "geng": "geng",
    "gengesports": "geng",
    "lyon": "lyon",
    "sgw": "saigonwarriors",
    "t1": "t1",
    "teamsecretwhales": "tsw",
    "tsw": "tsw",
}

SUBSTRING_CONFIDENCE_CAP = 0.89
TIME_TOLERANCE_SECONDS = 30 * 60


def resolve_market_to_game(
    market: Market,
    match: Match,
    games: list[Game],
    min_confidence: float = 0.9,
) -> ResolvedMarket | None:
    return resolve_market_attempt(market, match, games, min_confidence).resolved_market


def resolve_market_attempt(
    market: Market,
    match: Match,
    games: list[Game],
    min_confidence: float = 0.9,
    require_start_time: bool = True,
) -> MarketResolutionAttempt:
    if market.market_type != "game_winner":
        return _skip_attempt(market, match, None, 0.0, "non_game_winner")

    game_number = _extract_game_number(market)
    if game_number is None:
        return _skip_attempt(market, match, None, 0.0, "ambiguous_game_number")

    game = next((candidate for candidate in games if candidate.game_number == game_number), None)
    if game is None:
        return _skip_attempt(market, match, game_number, 0.0, "ambiguous_game_number")

    if len(market.outcomes) < 2 or len(market.token_ids) < 2:
        return _skip_attempt(market, match, game_number, 0.0, "ambiguous_token_outcomes", game)

    direct = _score_pair(market, match, swapped=False)
    swapped = _score_pair(market, match, swapped=True)
    best = swapped if swapped["confidence"] > direct["confidence"] else direct
    confidence = best["confidence"]
    evidence = {"direct": direct, "swapped": swapped}

    if confidence < min_confidence or any(score < min_confidence for score in best["scores"]):
        return _skip_attempt(market, match, game_number, confidence, "team_mismatch", game, evidence)

    time_status = _time_status(market, match)
    if require_start_time and time_status == "missing_start_time":
        return _skip_attempt(market, match, game_number, confidence, "missing_start_time", game, evidence)
    if time_status == "time_mismatch":
        return _skip_attempt(market, match, game_number, confidence, "time_mismatch", game, evidence)

    token_mappings = _token_mappings(market, match, game, best["order"])
    if len(token_mappings) < 2:
        return _skip_attempt(market, match, game_number, confidence, "team_side_unknown", game, evidence)

    resolved = ResolvedMarket(
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
    return MarketResolutionAttempt(
        market_slug=market.slug,
        match_id=match.match_id,
        game_id=game.game_id,
        game_number=game.game_number,
        mapping_confidence=confidence,
        status="mapped",
        skip_reason=None,
        resolved_market=resolved,
        token_mappings=token_mappings,
        evidence=evidence,
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
        attempts: list[tuple[Match, MarketResolutionAttempt]] = []
        for match in matches:
            attempt = resolve_market_attempt(
                market,
                match,
                storage.list_games_for_match(match.match_id),
                min_confidence=min_confidence,
            )
            attempts.append((match, attempt))

        match, attempt = _select_attempt(market, attempts, min_confidence)
        game = _attempt_game(attempt, storage.list_games_for_match(match.match_id))
        storage.insert_resolved_market_attempt(
            market=market,
            match=match,
            game=game,
            mapping_confidence=attempt.mapping_confidence,
            market_status=attempt.resolved_market.market_status if attempt.resolved_market else "skipped",
            skip_reason=attempt.skip_reason,
            raw_mapping=attempt_to_dict(attempt),
        )
        if attempt.resolved_market is None:
            skipped_count += 1
        else:
            resolved_count += 1

    return {"markets_seen": markets_seen, "resolved": resolved_count, "skipped": skipped_count}


def attempt_to_dict(attempt: MarketResolutionAttempt) -> dict:
    data = asdict(attempt)
    data["tokenMappings"] = data.pop("token_mappings")
    data["resolvedMarket"] = data.pop("resolved_market")
    data["marketSlug"] = data.pop("market_slug")
    data["matchId"] = data.pop("match_id")
    data["gameId"] = data.pop("game_id")
    data["gameNumber"] = data.pop("game_number")
    data["mappingConfidence"] = data.pop("mapping_confidence")
    data["skipReason"] = data.pop("skip_reason")
    return data


def build_mapping_artifact(paths: list[str | Path]) -> dict:
    samples = [_artifact_sample(Path(path)) for path in paths]
    mapped_count = sum(1 for sample in samples if sample["status"] == "mapped")
    skipped_count = sum(1 for sample in samples if sample["status"] == "skipped")
    return {
        "scope": "CAL-68 MarketResolver v1 fixture regression",
        "minMappingConfidence": 0.9,
        "samples": samples,
        "summary": {
            "sampleCount": len(samples),
            "mappedSamples": mapped_count,
            "skippedSamples": skipped_count,
            "availabilityStatus": "ok" if mapped_count >= 3 else "insufficient_market",
            "availabilityReason": (
                "At least three high-confidence same-event samples are available."
                if mapped_count >= 3
                else "Fewer than three high-confidence same-event samples are available in checked-in source-spike artifacts."
            ),
        },
        "notes": [
            "Structured fixture artifact only; source samples remain the raw evidence.",
            "Mapped records require mappingConfidence >= 0.90.",
            "Evidence shortages are marked insufficient_market rather than forced.",
        ],
    }


def team_name_confidence(left: str, right: str) -> float:
    left_norm = _canonical_team_name(left)
    right_norm = _canonical_team_name(right)
    if left_norm == right_norm:
        return 1.0
    if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
        return SUBSTRING_CONFIDENCE_CAP
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _pair_confidence(left_a: str, left_b: str, right_a: str, right_b: str) -> float:
    return (team_name_confidence(left_a, right_a) + team_name_confidence(left_b, right_b)) / 2


def _score_pair(market: Market, match: Match, swapped: bool) -> dict:
    right_names = (
        (match.team_b_name, match.team_a_name) if swapped else (match.team_a_name, match.team_b_name)
    )
    scores = [
        team_name_confidence(market.outcomes[0], right_names[0]),
        team_name_confidence(market.outcomes[1], right_names[1]),
    ]
    return {
        "confidence": sum(scores) / len(scores),
        "scores": scores,
        "order": [1, 0] if swapped else [0, 1],
        "marketOutcomes": market.outcomes[:2],
        "matchTeams": list(right_names),
    }


def _token_mappings(
    market: Market,
    match: Match,
    game: Game,
    order: list[int],
) -> list[TokenTeamMapping]:
    teams = [
        {"id": match.team_a_id, "name": match.team_a_name},
        {"id": match.team_b_id, "name": match.team_b_name},
    ]
    mappings: list[TokenTeamMapping] = []
    for outcome, token_id, team_index in zip(market.outcomes, market.token_ids, order, strict=False):
        team = teams[team_index]
        side = _team_side(team["id"], game)
        if side is None:
            continue
        mappings.append(
            TokenTeamMapping(
                token_outcome=outcome,
                token_id=token_id,
                team_id=team["id"],
                team_name=team["name"],
                team_side=side,
            )
        )
    return mappings


def _team_side(team_id: str, game: Game) -> str | None:
    if team_id == game.blue_team_id:
        return "blue"
    if team_id == game.red_team_id:
        return "red"
    return None


def _skip_attempt(
    market: Market,
    match: Match,
    game_number: int | None,
    confidence: float,
    reason: str,
    game: Game | None = None,
    evidence: dict | None = None,
) -> MarketResolutionAttempt:
    return MarketResolutionAttempt(
        market_slug=market.slug,
        match_id=match.match_id,
        game_id=game.game_id if game else None,
        game_number=game_number,
        mapping_confidence=confidence,
        status="skipped",
        skip_reason=reason,
        evidence=evidence or {},
    )


def _select_attempt(
    market: Market,
    attempts: list[tuple[Match, MarketResolutionAttempt]],
    min_confidence: float,
) -> tuple[Match, MarketResolutionAttempt]:
    if not attempts:
        fallback = Match(
            match_id="unresolved",
            league=None,
            team_a_id="unknown",
            team_a_name="unknown",
            team_b_id="unknown",
            team_b_name="unknown",
        )
        return fallback, _skip_attempt(market, fallback, _extract_game_number(market), 0.0, "no_match_candidates")

    mapped = [(match, attempt) for match, attempt in attempts if attempt.resolved_market is not None]
    if len(mapped) == 1:
        match, attempt = mapped[0]
        time_status = _time_status(market, match)
        if time_status == "missing_start_time":
            return match, _skip_attempt(
                market,
                match,
                attempt.game_number,
                attempt.mapping_confidence,
                "missing_start_time",
                _game_from_attempt(attempt),
                attempt.evidence,
            )
        return mapped[0]
    if len(mapped) > 1:
        timed = [
            (match, attempt)
            for match, attempt in mapped
            if _time_status(market, match) == "time_match"
        ]
        if len(timed) == 1:
            return timed[0]
        match, attempt = max(mapped, key=lambda item: item[1].mapping_confidence)
        return match, _skip_attempt(
            market,
            match,
            attempt.game_number,
            attempt.mapping_confidence,
            "ambiguous_match_candidates",
            _game_from_attempt(attempt),
            {"candidateMatchIds": [candidate.match_id for candidate, _ in mapped]},
        )

    return max(attempts, key=lambda item: item[1].mapping_confidence)


def _attempt_game(attempt: MarketResolutionAttempt, games: list[Game]) -> Game:
    if attempt.game_id is not None:
        for game in games:
            if game.game_id == attempt.game_id:
                return game
    if games:
        return games[0]
    game_number = attempt.game_number or 0
    return Game(
        game_id=f"{attempt.match_id}:unresolved:{game_number}",
        match_id=attempt.match_id,
        game_number=game_number,
        blue_team_id="unknown",
        red_team_id="unknown",
        state="unknown",
    )


def _game_from_attempt(attempt: MarketResolutionAttempt) -> Game | None:
    if attempt.game_id is None:
        return None
    return Game(
        game_id=attempt.game_id,
        match_id=attempt.match_id,
        game_number=attempt.game_number or 0,
        blue_team_id="unknown",
        red_team_id="unknown",
        state="unknown",
    )


def _time_status(market: Market, match: Match) -> str:
    market_start = _market_start_time(market)
    if market_start is None or match.start_time is None:
        return "missing_start_time"
    try:
        market_dt = _parse_time(market_start)
        match_dt = _parse_time(match.start_time)
    except ValueError:
        return "missing_start_time"
    if abs((market_dt - match_dt).total_seconds()) > TIME_TOLERANCE_SECONDS:
        return "time_mismatch"
    return "time_match"


def _market_start_time(market: Market) -> str | None:
    for key in ("startTime", "start_time", "startDate", "startDateIso"):
        value = market.raw.get(key)
        if isinstance(value, str):
            return value
    return None


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_sample(path: Path) -> dict:
    data = json.loads(path.read_text())
    confidence = float(data.get("mappingConfidence") or 0.0)
    raw_records = data.get("sampleMappings") or []
    mapped = confidence >= 0.9
    skip_reason = None if mapped else _artifact_skip_reason(data)
    records = [
        {
            "marketSlug": record.get("marketSlug"),
            "matchId": record.get("lolesportsMatchId"),
            "gameId": record.get("lolesportsGameId"),
            "teamSide": record.get("teamSide"),
            "tokenOutcome": record.get("outcome"),
            "tokenId": record.get("tokenId"),
            "mappingConfidence": float(record.get("mappingConfidence") or confidence),
            "skipReason": record.get("skipReason") if not mapped else None,
        }
        for record in raw_records
    ]
    return {
        "sourcePath": str(path),
        "polymarketEventSlug": data.get("polymarketEventSlug"),
        "matchId": data.get("lolesportsMatchId"),
        "mappingConfidence": confidence,
        "status": "mapped" if mapped else "skipped",
        "skipReason": skip_reason,
        "records": records,
    }


def _artifact_skip_reason(data: dict) -> str:
    for record in data.get("sampleMappings") or []:
        if record.get("skipReason"):
            return str(record["skipReason"])
    return f"mapping_confidence_below_{0.9:.2f}"


def _canonical_team_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    normalized = normalized.removesuffix("esports")
    normalized = normalized.removesuffix("gaming")
    return ALIASES.get(normalized, normalized)


def _extract_game_number(market: Market) -> int | None:
    text = f"{market.slug} {market.title}".lower()
    match = re.search(r"game\s*-?\s*(\d+)", text)
    return int(match.group(1)) if match else None
