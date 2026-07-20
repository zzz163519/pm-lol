#!/usr/bin/env python3
"""Read-only Polymarket LoL discovery and pre-match mapping smoke script."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import requests


POLYMARKET_LOL_URL = "https://polymarket.com/esports/league-of-legends"
GAMMA_EVENT_BY_SLUG_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_BOOK_URL = "https://clob.polymarket.com/book?token_id={token_id}"
LOLESPORTS_EVENT_URL = (
    "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={match_id}"
)
LOLESPORTS_SCHEDULE_URL = "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US"
LOLESPORTS_API_KEY_ENV = "LOLESPORTS_API_KEY"
BLG_T1_MATCH_ID = "115570934355614527"


def load_lolesports_api_key() -> str:
    api_key = os.environ.get(LOLESPORTS_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{LOLESPORTS_API_KEY_ENV} is required")
    return api_key


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def classify_error_message(message: str) -> str:
    lower = message.lower()
    if "ssl" in lower or "eof occurred" in lower or "connection closed" in lower:
        return "ssl_error"
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "parse" in lower or "json" in lower:
        return "parse_error"
    return "network_error"


def classify_http_status(status_code: int) -> str | None:
    if status_code >= 400:
        return "http_error"
    return None


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def name_similarity(left: str, right: str) -> float:
    left_norm = normalize_name(left)
    right_norm = normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.95
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def proxy_env() -> dict[str, bool]:
    return {
        key: bool(os.environ.get(key))
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
    }


def fetch(
    session: requests.Session,
    url: str,
    diagnostics: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    retries: int = 3,
    expect_json: bool = False,
) -> tuple[Any | None, dict[str, Any]]:
    record: dict[str, Any] = {
        "url": url,
        "attempts": 0,
        "retryCount": 0,
        "ok": False,
        "statusCode": None,
        "errorClass": None,
        "error": None,
        "priorErrors": [],
    }

    for attempt in range(1, retries + 1):
        record["attempts"] = attempt
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            record["statusCode"] = response.status_code
            error_class = classify_http_status(response.status_code)
            if error_class:
                record["errorClass"] = error_class
                record["error"] = f"HTTP {response.status_code}"
                if attempt < retries:
                    record["priorErrors"].append({"attempt": attempt, "errorClass": error_class, "error": record["error"]})
                    record["retryCount"] += 1
                    time.sleep(0.5 * attempt)
                    continue
                break

            if expect_json:
                try:
                    data = response.json()
                except ValueError as exc:
                    record["errorClass"] = "parse_error"
                    record["error"] = str(exc)
                    if attempt < retries:
                        record["priorErrors"].append(
                            {"attempt": attempt, "errorClass": "parse_error", "error": str(exc)}
                        )
                        record["retryCount"] += 1
                        time.sleep(0.5 * attempt)
                        continue
                    break
            else:
                data = response.text

            record["ok"] = True
            record["bytes"] = len(response.content)
            record["errorClass"] = None
            record["error"] = None
            diagnostics["requests"].append(record)
            return data, record
        except requests.RequestException as exc:
            record["errorClass"] = classify_error_message(str(exc))
            record["error"] = str(exc)
            if attempt < retries:
                record["priorErrors"].append(
                    {"attempt": attempt, "errorClass": record["errorClass"], "error": str(exc)}
                )
                record["retryCount"] += 1
                time.sleep(0.5 * attempt)
                continue

    diagnostics["requests"].append(record)
    return None, record


def extract_lol_event_slugs(html: str) -> list[str]:
    pattern = re.compile(r"lol-[a-z0-9]+-[a-z0-9]+-2026-\d{2}-\d{2}")
    return sorted(set(pattern.findall(html)))


def extract_game_number(market: dict[str, Any]) -> int | None:
    text = " ".join(str(market.get(key) or "") for key in ("slug", "question", "title"))
    match = re.search(r"(?:game[-\s]?)([1-5])(?:\D|$)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def is_game_winner_market(market: dict[str, Any]) -> bool:
    text = " ".join(str(market.get(key) or "") for key in ("slug", "question", "title"))
    return bool(re.search(r"game[-\s]?[1-5].*winner", text, re.IGNORECASE))


def market_to_summary(market: dict[str, Any], *, event_slug: str | None = None) -> dict[str, Any]:
    outcomes = parse_jsonish(market.get("outcomes"))
    token_ids = parse_jsonish(market.get("clobTokenIds"))
    return {
        "eventSlug": event_slug,
        "marketSlug": market.get("slug"),
        "question": market.get("question") or market.get("title"),
        "gameNumber": extract_game_number(market),
        "conditionId": market.get("conditionId"),
        "outcomes": outcomes if isinstance(outcomes, list) else [],
        "clobTokenIds": token_ids if isinstance(token_ids, list) else [],
        "active": market.get("active"),
        "closed": market.get("closed"),
    }


def filter_game_winner_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [market_to_summary(market) for market in markets if is_game_winner_market(market)]


def title_teams(title: str | None) -> list[str]:
    if not title or " vs " not in title:
        return []
    cleaned = re.sub(r"^LoL:\s*", "", title)
    cleaned = re.sub(r"\s*\(BO\d+\).*", "", cleaned)
    cleaned = re.sub(r"\s+-\s+.*", "", cleaned)
    left, right = cleaned.split(" vs ", 1)
    return [left.strip(), right.strip()]


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    title = event.get("title") or event.get("question")
    markets = event.get("markets") or []
    series_market = next((m for m in markets if m.get("slug") == event.get("slug")), None)
    teams = title_teams(title)
    if not teams and series_market:
        outcomes = parse_jsonish(series_market.get("outcomes"))
        if isinstance(outcomes, list):
            teams = outcomes
    return {
        "eventSlug": event.get("slug"),
        "title": title,
        "startTime": event.get("startTime") or event.get("startDate"),
        "teams": teams,
        "seriesMarket": market_to_summary(series_market, event_slug=event.get("slug")) if series_market else None,
    }


def summarize_book(market: dict[str, Any], token_id: str, outcome: str, book: dict[str, Any]) -> dict[str, Any]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []

    def prices(levels: list[dict[str, Any]]) -> list[float]:
        values: list[float] = []
        for level in levels:
            try:
                values.append(float(level.get("price")))
            except (TypeError, ValueError):
                pass
        return values

    bid_prices = prices(bids)
    ask_prices = prices(asks)
    return {
        "marketSlug": market.get("marketSlug"),
        "conditionId": market.get("conditionId") or book.get("market"),
        "tokenId": token_id,
        "outcome": outcome,
        "bidCount": len(bids),
        "askCount": len(asks),
        "bestBid": max(bid_prices) if bid_prices else None,
        "bestAsk": min(ask_prices) if ask_prices else None,
        "sourceTimestamp": book.get("timestamp"),
    }


def extract_lolesports_metadata(payload: dict[str, Any], match_id: str) -> dict[str, Any]:
    event = ((payload.get("data") or {}).get("event") or {}) if isinstance(payload, dict) else {}
    match = event.get("match") or {}
    teams = match.get("teams") or []
    games = match.get("games") or []
    league = event.get("league") or {}
    return {
        "matchId": str(event.get("id") or match_id),
        "eventId": str(event.get("id") or match_id),
        "startTime": event.get("startTime"),
        "state": event.get("state"),
        "league": league.get("name") or league.get("slug"),
        "leagueSlug": league.get("slug"),
        "teams": [
            {
                "id": team.get("id"),
                "name": team.get("name"),
                "code": team.get("code"),
            }
            for team in teams
        ],
        "games": [
            {
                "id": game.get("id"),
                "number": game.get("number"),
                "state": game.get("state"),
                "teams": game.get("teams") or [],
            }
            for game in games
        ],
    }


def find_schedule_event(payload: Any, match_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        event = payload.get("event") if "event" in payload else payload
        match = event.get("match") if isinstance(event, dict) else None
        if isinstance(match, dict) and str(match.get("id")) == match_id:
            return event
        for value in payload.values():
            found = find_schedule_event(value, match_id)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_schedule_event(item, match_id)
            if found:
                return found
    return None


def merge_schedule_metadata(metadata: dict[str, Any], schedule_event: dict[str, Any]) -> dict[str, Any]:
    if not metadata.get("startTime"):
        metadata["startTime"] = schedule_event.get("startTime")
    if not metadata.get("state"):
        metadata["state"] = schedule_event.get("state")
    league = schedule_event.get("league") or {}
    if not metadata.get("league"):
        metadata["league"] = league.get("name") or league.get("slug")
    if not metadata.get("leagueSlug"):
        metadata["leagueSlug"] = league.get("slug")
    return metadata


def fetch_lolesports_event(
    session: requests.Session,
    diagnostics: dict[str, Any],
    match_id: str = BLG_T1_MATCH_ID,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    api_key = api_key or load_lolesports_api_key()
    url = LOLESPORTS_EVENT_URL.format(match_id=match_id)
    payload, record = fetch(
        session,
        url,
        diagnostics,
        headers={"x-api-key": api_key},
        timeout=20.0,
        retries=2,
        expect_json=True,
    )
    if not record.get("ok") or not isinstance(payload, dict):
        return {
            "ok": False,
            "matchId": match_id,
            "errorClass": record.get("errorClass") or "empty_result",
            "error": record.get("error"),
            "metadata": None,
        }
    metadata = extract_lolesports_metadata(payload, match_id)
    schedule_payload, schedule_record = fetch(
        session,
        LOLESPORTS_SCHEDULE_URL,
        diagnostics,
        headers={"x-api-key": api_key},
        timeout=20.0,
        retries=3,
        expect_json=True,
    )
    schedule_event = find_schedule_event(schedule_payload, match_id) if schedule_record.get("ok") else None
    if schedule_event:
        metadata = merge_schedule_metadata(metadata, schedule_event)
    return {
        "ok": True,
        "matchId": match_id,
        "metadata": metadata,
        "scheduleLookup": {
            "ok": bool(schedule_event),
            "errorClass": None if schedule_event else schedule_record.get("errorClass") or "empty_result",
            "error": None if schedule_event else schedule_record.get("error"),
        },
    }


def build_mapping_candidate(
    event: dict[str, Any] | None,
    game_winner_markets: list[dict[str, Any]],
    lolesports: dict[str, Any],
    *,
    expected_match_id: str | None = BLG_T1_MATCH_ID,
) -> dict[str, Any]:
    event = event or {}
    metadata = lolesports.get("metadata") or {}
    pm_teams = event.get("teams") or []
    lol_teams = metadata.get("teams") or []
    aliases = build_team_aliases(pm_teams, lol_teams)
    lol_names = [team.get("name") for team in lol_teams if team.get("name")]
    lol_codes = [team.get("code") for team in lol_teams if team.get("code")]
    normalized_lol = {normalize_name(name) for name in [*lol_names, *lol_codes]}

    team_score = 0.0
    if pm_teams:
        matched = 0
        for team in pm_teams:
            candidates = aliases.get(team, [team])
            if any(normalize_name(candidate) in normalized_lol for candidate in candidates):
                matched += 1
        team_score = matched / len(pm_teams)

    start_score = 1.0 if event.get("startTime") and event.get("startTime") == metadata.get("startTime") else 0.0
    match_id_score = (
        1.0
        if expected_match_id and str(metadata.get("matchId")) == str(expected_match_id)
        else 0.0
    )
    game_numbers = sorted(
        market.get("gameNumber") for market in game_winner_markets if market.get("gameNumber") is not None
    )
    game_score = 1.0 if game_numbers[:4] == [1, 2, 3, 4] else 0.75 if game_numbers else 0.0

    confidence = round((team_score * 0.45) + (start_score * 0.25) + (match_id_score * 0.15) + (game_score * 0.15), 4)
    sample_mappings = build_token_side_samples(
        game_winner_markets,
        metadata,
        aliases,
        event_confidence=confidence,
    )
    return {
        "polymarketEventSlug": event.get("eventSlug"),
        "polymarketTitle": event.get("title"),
        "polymarketStartTime": event.get("startTime"),
        "polymarketTeams": pm_teams,
        "polymarketGameWinnerMarkets": game_winner_markets,
        "lolesportsMatchId": expected_match_id,
        "lolesports": lolesports,
        "teamAliasMapping": aliases,
        "startTimeAligned": bool(start_score),
        "mappingConfidence": confidence,
        "viable": confidence >= 0.90,
        "sampleMappings": sample_mappings,
        "pendingLiveValidation": True,
        "notes": [
            "Pre-match static mapping smoke only.",
            "LoLEsports live latency is not validated by this output.",
            "Token-to-side samples are gated at mappingConfidence >= 0.90.",
        ],
    }


def build_team_aliases(pm_teams: list[str], lol_teams: list[dict[str, Any]]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for pm_team in pm_teams:
        values = [pm_team]
        best_team, confidence = best_team_match(pm_team, lol_teams, {})
        if best_team and confidence >= 0.90:
            for value in (best_team.get("name"), best_team.get("code")):
                if value and value not in values:
                    values.append(value)
        aliases[pm_team] = values
    return aliases


def build_token_side_samples(
    game_winner_markets: list[dict[str, Any]],
    metadata: dict[str, Any],
    aliases: dict[str, list[str]],
    *,
    event_confidence: float,
    min_confidence: float = 0.90,
) -> list[dict[str, Any]]:
    teams = metadata.get("teams") or []
    games = metadata.get("games") or []
    match_id = str(metadata.get("matchId") or "")
    event_id = str(metadata.get("eventId") or match_id)
    samples: list[dict[str, Any]] = []

    for market in game_winner_markets:
        game_number = market.get("gameNumber")
        game = next((candidate for candidate in games if candidate.get("number") == game_number), None)
        outcomes = market.get("outcomes") or []
        token_ids = market.get("clobTokenIds") or []

        for index, token_id in enumerate(token_ids):
            outcome = str(outcomes[index]) if index < len(outcomes) else "unknown"
            team, team_confidence = best_team_match(outcome, teams, aliases)
            confidence = round(min(event_confidence, team_confidence), 4)
            game_team = find_game_team(game, team.get("id") if team else None) if game else None
            skip_reason = mapping_skip_reason(confidence, min_confidence, game, team, game_team)

            samples.append(
                {
                    "status": "skipped" if skip_reason else "mapped",
                    "polymarketTitle": market.get("question"),
                    "marketSlug": market.get("marketSlug"),
                    "conditionId": market.get("conditionId"),
                    "tokenId": str(token_id),
                    "outcome": outcome,
                    "lolesportsMatchId": match_id,
                    "lolesportsEventId": event_id,
                    "lolesportsGameId": str(game.get("id")) if game else None,
                    "gameNumber": game_number,
                    "teamId": str(team.get("id")) if team else None,
                    "teamName": team.get("name") if team else None,
                    "teamCode": team.get("code") if team else None,
                    "teamSide": game_team.get("side") if game_team else None,
                    "mappingConfidence": confidence,
                    "skipReason": skip_reason,
                }
            )

    return samples


def best_team_match(
    outcome: str,
    teams: list[dict[str, Any]],
    aliases: dict[str, list[str]],
) -> tuple[dict[str, Any] | None, float]:
    outcome_aliases = aliases.get(outcome, [outcome])
    best_team: dict[str, Any] | None = None
    best_confidence = 0.0

    for team in teams:
        identifiers = [str(value) for value in (team.get("name"), team.get("code")) if value]
        confidence = max(
            (name_similarity(alias, identifier) for alias in outcome_aliases for identifier in identifiers),
            default=0.0,
        )
        if confidence > best_confidence:
            best_team = team
            best_confidence = confidence

    return best_team, round(best_confidence, 4)


def find_game_team(game: dict[str, Any] | None, team_id: Any) -> dict[str, Any] | None:
    if not game or team_id is None:
        return None
    team_id_text = str(team_id)
    return next(
        (team for team in game.get("teams") or [] if str(team.get("id")) == team_id_text),
        None,
    )


def mapping_skip_reason(
    confidence: float,
    min_confidence: float,
    game: dict[str, Any] | None,
    team: dict[str, Any] | None,
    game_team: dict[str, Any] | None,
) -> str | None:
    if confidence < min_confidence:
        return f"mapping_confidence_below_{min_confidence:.2f}"
    if game is None:
        return "lolesports_game_not_found"
    if team is None:
        return "lolesports_team_not_found"
    if game_team is None:
        return "lolesports_team_side_not_found"
    return None


def build_result(args: argparse.Namespace, *, lolesports_api_key: str | None = None) -> dict[str, Any]:
    lolesports_api_key = lolesports_api_key or load_lolesports_api_key()
    observed_at = utc_now()
    diagnostics: dict[str, Any] = {
        "proxyEnv": proxy_env(),
        "requests": [],
        "errorClasses": [],
    }
    warnings = [
        "Gamma generic keyword search is unreliable for LoL discovery.",
        "Game 5 Winner was not observed in the current documented samples.",
        "Polymarket Market WebSocket remains pending_network_retest.",
        "This is read-only source proof, not strategy, signal, execution, or live-latency validation.",
    ]
    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-polymarket-discovery-smoke/0.1"})

    html, html_record = fetch(session, POLYMARKET_LOL_URL, diagnostics, retries=args.retries)
    slugs = extract_lol_event_slugs(html) if isinstance(html, str) else []
    if not slugs:
        diagnostics["errorClasses"].append(html_record.get("errorClass") or "empty_result")
        warnings.append("No LoL event slugs were extracted from the Polymarket page.")

    all_events: list[dict[str, Any]] = []
    all_winners: list[dict[str, Any]] = []
    target_event: dict[str, Any] | None = None

    prioritized_slugs = [args.target_event_slug] if args.target_event_slug else []
    prioritized_slugs.extend(slug for slug in slugs if slug not in prioritized_slugs)

    for slug in prioritized_slugs[: args.max_events]:
        payload, record = fetch(
            session,
            GAMMA_EVENT_BY_SLUG_URL.format(slug=slug),
            diagnostics,
            retries=args.retries + 3 if slug == args.target_event_slug else args.retries,
            expect_json=True,
        )
        if not record.get("ok") or not isinstance(payload, dict):
            diagnostics["errorClasses"].append(record.get("errorClass") or "empty_result")
            continue
        event = event_summary(payload)
        all_events.append(event)
        winners = filter_game_winner_markets(payload.get("markets") or [])
        for winner in winners:
            winner["eventSlug"] = slug
        all_winners.extend(winners)
        if slug == args.target_event_slug:
            target_event = event

    orderbook_samples: list[dict[str, Any]] = []
    preferred_market = next(
        (
            market
            for market in all_winners
            if market.get("eventSlug") == args.target_event_slug and market.get("gameNumber") == 1
        ),
        None,
    )
    book_candidates = []
    if preferred_market:
        book_candidates.append(preferred_market)
    book_candidates.extend(market for market in all_winners if market is not preferred_market)

    if book_candidates:
        for candidate in book_candidates:
            outcomes = candidate.get("outcomes") or []
            token_ids = candidate.get("clobTokenIds") or []
            if not token_ids:
                continue
            for index, token_id in enumerate(token_ids):
                outcome = str(outcomes[index]) if index < len(outcomes) else "unknown"
                book, book_record = fetch(
                    session,
                    CLOB_BOOK_URL.format(token_id=str(token_id)),
                    diagnostics,
                    retries=args.retries,
                    expect_json=True,
                )
                if book_record.get("ok") and isinstance(book, dict):
                    orderbook_samples.append(summarize_book(candidate, str(token_id), outcome, book))
                    break
                diagnostics["errorClasses"].append(book_record.get("errorClass") or "empty_result")
            if orderbook_samples:
                break
        if not orderbook_samples:
            warnings.append("All attempted CLOB book reads failed; failures are recorded in networkDiagnostics.")
    else:
        diagnostics["errorClasses"].append("empty_result")
        warnings.append("No Game Winner market was available for CLOB book sampling.")

    lolesports = fetch_lolesports_event(
        session,
        diagnostics,
        args.lolesports_match_id,
        api_key=lolesports_api_key,
    )
    if not lolesports.get("ok"):
        diagnostics["errorClasses"].append(lolesports.get("errorClass") or "empty_result")
        warnings.append("LoLEsports event metadata could not be read; mapping sample records the error.")

    if target_event is None:
        target_event = next((event for event in all_events if event.get("eventSlug") == args.target_event_slug), None)

    target_markets = [
        market for market in all_winners if market.get("eventSlug") == args.target_event_slug
    ]
    mapping_candidate = build_mapping_candidate(
        target_event,
        target_markets,
        lolesports,
        expected_match_id=args.lolesports_match_id,
    )

    diagnostics["errorClasses"] = sorted(set(filter(None, diagnostics["errorClasses"])))
    diagnostics["totalRequests"] = len(diagnostics["requests"])
    diagnostics["totalRetries"] = sum(record.get("retryCount", 0) for record in diagnostics["requests"])

    return {
        "observedAt": observed_at,
        "networkDiagnostics": diagnostics,
        "events": all_events,
        "gameWinnerMarkets": all_winners,
        "orderbookSamples": orderbook_samples,
        "mappingCandidate": mapping_candidate,
        "warnings": warnings,
    }


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Write full discovery smoke JSON to this path.")
    parser.add_argument(
        "--mapping-output",
        help="Write only mappingCandidate JSON to this path.",
    )
    parser.add_argument("--target-event-slug", default="lol-blg-t1-2026-07-04")
    parser.add_argument("--lolesports-match-id", default=BLG_T1_MATCH_ID)
    parser.add_argument("--max-events", type=int, default=8)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = build_result(args, lolesports_api_key=load_lolesports_api_key())
    if args.output:
        write_json(args.output, result)
    if args.mapping_output:
        write_json(args.mapping_output, result["mappingCandidate"])
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
