#!/usr/bin/env python3
"""Read-only Cito live + Polymarket CLOB polling smoke for CAL-53."""

from __future__ import annotations

import argparse
import json
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import quote

import requests


CITO_BASE_URL = "https://api.citoapi.com/api/v1"
GAMMA_EVENT_BY_SLUG_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_MARKETS_URL = "https://clob.polymarket.com/markets?clob_token_ids={token_ids}"
DEFAULT_EVENT_SLUGS = ("lol-g2-t1-2026-07-08", "lol-ly-tsw-2026-07-08")


class ApiKeyLoadResult(NamedTuple):
    present: bool
    source: str | None
    length: int


HttpGet = Callable[[str], tuple[Any | None, dict[str, Any]]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(left: str | None, right: str | None) -> float | None:
    left_dt = parse_time(left)
    right_dt = parse_time(right)
    if not left_dt or not right_dt:
        return None
    return round(abs(right_dt.timestamp() - left_dt.timestamp()), 3)


def classify_error_message(message: str) -> str:
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "json" in lower or "parse" in lower:
        return "parse_error"
    if "ssl" in lower or "connection" in lower:
        return "network_error"
    return "request_error"


def load_cito_api_key(env_path: Path = Path(".env")) -> ApiKeyLoadResult:
    env_value = os.environ.get("CITO_API_KEY")
    if env_value:
        return ApiKeyLoadResult(present=True, source="environment", length=len(env_value))
    if not env_path.exists():
        return ApiKeyLoadResult(present=False, source=None, length=0)

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "CITO_API_KEY":
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ["CITO_API_KEY"] = value
                return ApiKeyLoadResult(present=True, source=".env", length=len(value))
    return ApiKeyLoadResult(present=False, source=".env", length=0)


def current_cito_api_key() -> str | None:
    value = os.environ.get("CITO_API_KEY")
    return value or None


def real_http_get(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[Any | None, dict[str, Any]]:
    observed_at = utc_now()
    try:
        response = session.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return None, {
            "observedAt": observed_at,
            "url": url,
            "ok": False,
            "statusCode": None,
            "errorClass": classify_error_message(str(exc)),
            "error": str(exc),
        }

    record = {
        "observedAt": observed_at,
        "url": url,
        "ok": 200 <= response.status_code < 300,
        "statusCode": response.status_code,
        "errorClass": "http_error" if response.status_code >= 400 else None,
        "error": None,
    }
    if not response.content:
        return None, record
    try:
        return response.json(), record
    except ValueError as exc:
        record["ok"] = False
        record["errorClass"] = "parse_error"
        record["error"] = str(exc)
        return None, record


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def extract_game_number(market: dict[str, Any]) -> int | None:
    text = " ".join(str(market.get(key) or "") for key in ("slug", "question", "title"))
    match = re.search(r"game[-\s]?([1-5]).*winner", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def game_winner_markets_from_event(payload: Any, event_slug: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    markets = []
    for market in payload.get("markets") or []:
        game_number = extract_game_number(market)
        if game_number is None:
            continue
        outcomes = parse_jsonish(market.get("outcomes"))
        token_ids = parse_jsonish(market.get("clobTokenIds"))
        if not isinstance(outcomes, list) or not isinstance(token_ids, list):
            continue
        markets.append(
            {
                "eventSlug": event_slug,
                "marketSlug": market.get("slug"),
                "question": market.get("question") or market.get("title"),
                "conditionId": market.get("conditionId"),
                "gameNumber": game_number,
                "outcomes": outcomes,
                "clobTokenIds": [str(token_id) for token_id in token_ids],
            }
        )
    return sorted(markets, key=lambda item: item["gameNumber"])


def discover_polymarket_tokens(event_slugs: list[str], http_get: HttpGet) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    markets = []
    for slug in event_slugs:
        payload, record = http_get(GAMMA_EVENT_BY_SLUG_URL.format(slug=slug))
        records.append({"eventSlug": slug, "request": record})
        if record.get("ok"):
            markets.extend(game_winner_markets_from_event(payload, slug))
        if markets:
            break
    return markets, records


def fetch_clob_markets(markets: list[dict[str, Any]], http_get: HttpGet) -> dict[str, Any]:
    token_ids = []
    for market in markets[:2]:
        token_ids.extend(market.get("clobTokenIds") or [])
    token_ids = token_ids[:20]
    if not token_ids:
        return {
            "status": "skipped_no_token_ids",
            "tokenIds": [],
            "request": None,
            "raw": None,
        }

    joined = ",".join(token_ids)
    payload, record = http_get(CLOB_MARKETS_URL.format(token_ids=quote(joined, safe=",")))
    return {
        "status": "ok" if record.get("ok") else "error",
        "tokenIds": token_ids,
        "request": record,
        "raw": payload,
    }


def find_match_list(schedule_payload: Any) -> list[dict[str, Any]]:
    found = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("gameId", "officialEventId", "matchId", "id")) and any(
                key in value for key in ("teams", "teamA", "teamB", "startTime", "state")
            ):
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schedule_payload)
    return found


def summarize_match(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": match.get("id") or match.get("matchId"),
        "gameId": match.get("gameId") or match.get("currentGameId"),
        "officialEventId": match.get("officialEventId") or match.get("eventId"),
        "state": match.get("state") or match.get("status"),
        "startTime": match.get("startTime") or match.get("scheduledStartTime"),
        "teams": match.get("teams") or [value for value in (match.get("teamA"), match.get("teamB")) if value],
    }


def discover_game_id(live_payload: Any) -> str | None:
    if isinstance(live_payload, dict):
        for key in ("gameId", "currentGameId", "matchId", "id"):
            value = live_payload.get(key)
            if value:
                return str(value)
        for key in ("game", "match", "data", "coverage"):
            value = discover_game_id(live_payload.get(key))
            if value:
                return value
    elif isinstance(live_payload, list):
        for item in live_payload:
            value = discover_game_id(item)
            if value:
                return value
    return None


def discover_visual_game_id(coverage_payload: Any) -> str | None:
    if not isinstance(coverage_payload, dict):
        return None
    active = coverage_payload.get("active_live_game_id")
    if active:
        return str(active)
    games = coverage_payload.get("games")
    if isinstance(games, list):
        for game in games:
            if not isinstance(game, dict):
                continue
            for key in ("esportsApiId", "gameId", "id"):
                value = game.get(key)
                if value:
                    return str(value).removeprefix("lol-game-")
    return None


def live_status(live_payload: Any) -> str | None:
    if not isinstance(live_payload, dict):
        return None
    status = live_payload.get("status") or live_payload.get("state")
    return str(status) if status is not None else None


def has_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def contains_key_name(value: Any, names: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if any(name in key_lower for name in names) and child not in (None, [], {}):
                return True
            if contains_key_name(child, names):
                return True
    elif isinstance(value, list):
        return any(contains_key_name(item, names) for item in value)
    return False


def visual_state_coverage(visual_state: Any, schedule_matches: list[dict[str, Any]]) -> dict[str, str]:
    if not isinstance(visual_state, dict):
        return {
            "gameClock": "missing_no_live_match",
            "gold": "missing_no_live_match",
            "objectives": "missing_no_live_match",
            "gameState": "missing_no_live_match",
            "winner": "missing_no_live_match",
            "finalPicks": "missing_no_live_match",
            "teamIdentity": "present" if schedule_matches else "missing",
        }

    return {
        "gameClock": "present" if contains_key_name(visual_state, ("gametime", "gameclock", "clock")) else "missing",
        "gold": "present" if contains_key_name(visual_state, ("gold",)) else "missing",
        "objectives": "present" if contains_key_name(visual_state, ("dragon", "baron", "tower", "objective")) else "missing",
        "gameState": "present" if contains_key_name(visual_state, ("gamestate", "state")) else "missing",
        "winner": "present" if contains_key_name(visual_state, ("winner",)) else "missing",
        "finalPicks": "present" if contains_key_name(visual_state, ("pick", "champion")) else "missing",
        "teamIdentity": "present" if contains_key_name(visual_state, ("team", "name", "code")) else "missing",
    }


def is_visual_state_ready(visual_state: Any) -> bool:
    if not isinstance(visual_state, dict):
        return False
    status = str(visual_state.get("status") or "").lower()
    if status in {"not_ready", "unavailable", "error"}:
        return False
    return visual_state.get("data") not in (None, [], {}) or any(
        contains_key_name(visual_state, names)
        for names in (("gametime", "gameclock", "clock"), ("gold",), ("dragon", "baron", "tower", "objective"))
    )


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_report(path: Path, result: dict[str, Any]) -> str:
    result["rawSamplePaths"]["report"] = str(path)
    return write_json(path, result)


def run_smoke(
    *,
    cito_api_key: str,
    output_dir: Path,
    event_slugs: list[str],
    poll_timeout_sec: int,
    poll_interval_sec: int,
    http_get: Callable[..., tuple[Any | None, dict[str, Any]]],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    started_at = now()
    cito_headers = {"x-api-key": cito_api_key}
    schedule_payload, schedule_record = http_get(f"{CITO_BASE_URL}/lol/schedule/today", headers=cito_headers)
    schedule_matches = [summarize_match(match) for match in find_match_list(schedule_payload)]

    live_payload = None
    live_record: dict[str, Any] = {}
    live_attempts = []
    deadline = time.monotonic() + poll_timeout_sec
    while True:
        live_payload, live_record = http_get(f"{CITO_BASE_URL}/lol/live", headers=cito_headers)
        status = live_status(live_payload)
        live_attempts.append({"status": status, "request": live_record, "payload": live_payload})
        if live_record.get("ok") and status != "no_match":
            break
        if time.monotonic() >= deadline:
            break
        sleep(poll_interval_sec)

    match_id = discover_game_id(live_payload)
    game_id = match_id
    visual_payload = None
    visual_record = None
    coverage_payload = None
    coverage_record = None
    stats_payload = None
    stats_record = None
    postgame_payload = None
    postgame_record = None
    if match_id:
        coverage_payload, coverage_record = http_get(
            f"{CITO_BASE_URL}/lol/matches/{match_id}/coverage",
            headers=cito_headers,
        )
        game_id = discover_visual_game_id(coverage_payload) or match_id
        visual_payload, visual_record = http_get(
            f"{CITO_BASE_URL}/lol/live/{game_id}/visual-state",
            headers=cito_headers,
        )
        if isinstance(visual_payload, dict) and not is_visual_state_ready(visual_payload):
            stats_payload, stats_record = http_get(
                f"{CITO_BASE_URL}/lol/live/{game_id}/stats",
                headers=cito_headers,
            )
            postgame_payload, postgame_record = http_get(
                f"{CITO_BASE_URL}/lol/games/{game_id}/postgame",
                headers=cito_headers,
            )

    markets, market_discovery_records = discover_polymarket_tokens(event_slugs, http_get)
    clob = fetch_clob_markets(markets, http_get)

    cito_ts = (visual_record or live_record or schedule_record).get("observedAt")
    polymarket_ts = ((clob.get("request") or {}) if isinstance(clob, dict) else {}).get("observedAt")
    coverage = visual_state_coverage(visual_payload, schedule_matches)

    raw_paths = {
        "scheduleToday": write_json(output_dir / "cito-schedule-today-dry-run-2026-07-08.json", schedule_payload),
        "live": write_json(output_dir / "cito-live-dry-run-2026-07-08.json", live_payload),
        "dryRun": write_json(output_dir / "cito-live-no-match-dry-run-2026-07-08.json", live_payload),
        "visualState": None,
        "coverage": None,
        "stats": None,
        "postgame": None,
        "polymarketClob": write_json(output_dir / "cito-polymarket-clob-dry-run-2026-07-08.json", clob.get("raw")),
        "report": "",
    }
    if visual_payload is not None:
        raw_paths["visualState"] = write_json(output_dir / f"cito-visual-state-{game_id}-2026-07-08.json", visual_payload)
    if coverage_payload is not None:
        raw_paths["coverage"] = write_json(output_dir / f"cito-coverage-{game_id}-2026-07-08.json", coverage_payload)
    if stats_payload is not None:
        raw_paths["stats"] = write_json(output_dir / f"cito-stats-{game_id}-2026-07-08.json", stats_payload)
    if postgame_payload is not None:
        raw_paths["postgame"] = write_json(output_dir / f"cito-postgame-{game_id}-2026-07-08.json", postgame_payload)

    visual_ready = is_visual_state_ready(visual_payload)
    if game_id and visual_record and visual_record.get("ok") and visual_ready:
        overall_status = "live_sample_collected"
    elif game_id and visual_record and visual_record.get("ok"):
        overall_status = "live_visual_state_not_ready"
    elif game_id and visual_record and not visual_record.get("ok"):
        overall_status = "live_visual_state_unavailable"
    elif live_status(live_payload) == "no_match" and live_record.get("ok"):
        overall_status = "no_match_timeout"
    elif not live_record.get("ok"):
        overall_status = "cito_live_error"
    else:
        overall_status = "live_without_game_id"

    result = {
        "script": "scripts/cito_live_polymarket_smoke.py",
        "startedAt": started_at,
        "endedAt": now(),
        "overallStatus": overall_status,
        "auth": {
            "apiKeyPresent": True,
            "apiKeyLength": len(cito_api_key),
            "headerName": "x-api-key",
        },
        "cito": {
            "baseUrl": CITO_BASE_URL,
            "scheduleToday": {
                "request": schedule_record,
                "matchCount": len(schedule_matches),
                "matches": schedule_matches,
            },
            "live": {
                "request": live_record,
                "status": live_status(live_payload),
                "matchId": match_id,
                "gameId": game_id,
                "attempts": len(live_attempts),
            },
            "visualState": {
                "request": visual_record,
                "gameId": game_id,
                "rawSamplePath": raw_paths["visualState"],
                "ready": visual_ready,
            },
            "coverage": {
                "request": coverage_record,
                "rawSamplePath": raw_paths["coverage"],
            },
            "stats": {
                "request": stats_record,
                "rawSamplePath": raw_paths["stats"],
            },
            "postgame": {
                "request": postgame_record,
                "rawSamplePath": raw_paths["postgame"],
            },
        },
        "polymarket": {
            "eventSlugsTried": event_slugs,
            "marketDiscovery": market_discovery_records,
            "gameWinnerMarkets": markets,
            "status": clob.get("status"),
            "clobTokenIds": clob.get("tokenIds"),
            "clobRequest": clob.get("request"),
            "clobRawSamplePath": raw_paths["polymarketClob"],
        },
        "timing": {
            "citoSnapshotAt": cito_ts,
            "polymarketSnapshotAt": polymarket_ts,
            "citoVsPolymarketDeltaSec": seconds_between(cito_ts, polymarket_ts),
        },
        "fieldCoverage": coverage,
        "rawSamplePaths": raw_paths,
        "boundaryFindings": [
            "read_only_smoke",
            "no_wallet",
            "no_private_key",
            "no_trade_execution",
            "no_strategy_or_signal",
        ],
    }
    write_report(output_dir / "cito-live-polymarket-smoke-2026-07-08.json", result)
    return result


def build_blocked_no_key_result(key_result: ApiKeyLoadResult, output_dir: Path) -> dict[str, Any]:
    result = {
        "script": "scripts/cito_live_polymarket_smoke.py",
        "observedAt": utc_now(),
        "overallStatus": "blocked_missing_cito_api_key",
        "auth": {
            "apiKeyPresent": key_result.present,
            "apiKeyLength": key_result.length,
            "source": key_result.source,
            "headerName": "x-api-key",
        },
        "rawSamplePaths": {},
        "boundaryFindings": [
            "no_cito_request_sent_without_api_key",
            "read_only_smoke",
            "no_wallet",
            "no_private_key",
            "no_trade_execution",
        ],
    }
    write_report(output_dir / "cito-live-polymarket-smoke-2026-07-08.json", result)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/source-spike")
    parser.add_argument("--poll-timeout-sec", type=int, default=900)
    parser.add_argument("--poll-interval-sec", type=int, default=30)
    parser.add_argument("--event-slug", action="append", dest="event_slugs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = Path(args.output_dir)
    key_result = load_cito_api_key(Path(".env"))
    api_key = current_cito_api_key()
    if not api_key:
        result = build_blocked_no_key_result(key_result, output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-cito-live-polymarket-smoke/0.1"})

    def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 15.0):
        return real_http_get(session, url, headers=headers, timeout=timeout)

    result = run_smoke(
        cito_api_key=api_key,
        output_dir=output_dir,
        event_slugs=args.event_slugs or list(DEFAULT_EVENT_SLUGS),
        poll_timeout_sec=args.poll_timeout_sec,
        poll_interval_sec=args.poll_interval_sec,
        http_get=http_get,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
