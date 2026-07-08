#!/usr/bin/env python3
"""Read-only dual-source field map probe for CAL-59."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import requests


CITO_BASE_URL = "https://api.citoapi.com/api/v1"
LOLESPORTS_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
LOLESPORTS_EVENT_DETAILS_URL = "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={match_id}"
LOLESPORTS_WINDOW_URL = "https://feed.lolesports.com/livestats/v1/window/{game_id}"
DEFAULT_TARGET_TEAMS = ("T1", "G2")


HttpGet = Callable[..., tuple[Any | None, dict[str, Any]]]


class ApiKeyLoadResult(NamedTuple):
    present: bool
    source: str | None
    length: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_stamp(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(".", "").replace("Z", "Z")


def load_cito_api_key(env_path: Path = Path(".env")) -> ApiKeyLoadResult:
    env_value = os.environ.get("CITO_API_KEY")
    if env_value:
        return ApiKeyLoadResult(True, "environment", len(env_value))
    if not env_path.exists():
        return ApiKeyLoadResult(False, None, 0)
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "CITO_API_KEY":
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ["CITO_API_KEY"] = value
            return ApiKeyLoadResult(True, ".env", len(value))
    return ApiKeyLoadResult(False, ".env", 0)


def classify_error(message: str) -> str:
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "json" in lower or "parse" in lower:
        return "parse_error"
    if "ssl" in lower or "connection" in lower:
        return "network_error"
    return "request_error"


def real_http_get(session: requests.Session, url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0) -> tuple[Any | None, dict[str, Any]]:
    observed_at = utc_now()
    started = time.monotonic()
    try:
        response = session.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return None, {
            "observedAt": observed_at,
            "elapsedSec": round(time.monotonic() - started, 3),
            "url": url,
            "ok": False,
            "statusCode": None,
            "errorClass": classify_error(str(exc)),
            "error": str(exc),
        }
    record = {
        "observedAt": observed_at,
        "elapsedSec": round(time.monotonic() - started, 3),
        "url": url,
        "ok": 200 <= response.status_code < 300 and bool(response.content),
        "statusCode": response.status_code,
        "errorClass": "rate_limited" if response.status_code == 429 else ("empty_body" if not response.content else ("http_error" if response.status_code >= 400 else None)),
        "error": None,
    }
    if not response.content or response.status_code >= 400:
        if response.content and response.status_code >= 400:
            record["error"] = response.text[:500]
        return None, record
    try:
        return response.json(), record
    except ValueError as exc:
        record["ok"] = False
        record["errorClass"] = "parse_error"
        record["error"] = str(exc)
        return None, record


def text_blob(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            parts.append(item)

    walk(value)
    return " ".join(parts).lower()


def normalize_cito_id(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    return str(value).removeprefix("lol-game-").removeprefix("lol-match-")


def skipped_record(reason: str) -> dict[str, Any]:
    return {"ok": False, "statusCode": None, "errorClass": reason}


def discover_target_match(payload: Any, target_teams: tuple[str, str]) -> dict[str, Any] | None:
    targets = tuple(team.lower() for team in target_teams)
    if isinstance(payload, dict):
        if ("matchId" in payload or "id" in payload) and all(team in text_blob(payload) for team in targets):
            return payload
        for child in payload.values():
            found = discover_target_match(child, target_teams)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = discover_target_match(child, target_teams)
            if found:
                return found
    return None


def discover_visual_game_id(coverage_payload: Any) -> str | None:
    if not isinstance(coverage_payload, dict):
        return None
    for key in ("active_live_game_id", "activeLiveGameId", "gameId", "currentGameId"):
        value = normalize_cito_id(coverage_payload.get(key))
        if value:
            return value
    games = coverage_payload.get("games")
    if isinstance(games, list):
        for game in games:
            if not isinstance(game, dict):
                continue
            for key in ("esportsApiId", "gameId", "id"):
                value = normalize_cito_id(game.get(key))
                if value:
                    return value
    return None


def sample_frame(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    frame = payload.get("sampleFrame")
    if isinstance(frame, dict):
        return frame
    frames = payload.get("frames")
    if isinstance(frames, list) and frames and isinstance(frames[-1], dict):
        return frames[-1]
    return None


def extract_draft_picks(window_payload: Any) -> dict[str, Any]:
    metadata = window_payload.get("gameMetadata") if isinstance(window_payload, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    picks: dict[str, list[str]] = {"blue": [], "red": []}
    for side, key in (("blue", "blueTeamMetadata"), ("red", "redTeamMetadata")):
        team = metadata.get(key)
        if not isinstance(team, dict):
            continue
        for participant in team.get("participantMetadata") or []:
            if isinstance(participant, dict) and participant.get("championId"):
                picks[side].append(str(participant["championId"]))
    return {
        "status": "present" if len(picks["blue"]) + len(picks["red"]) >= 10 else "missing",
        "source": "lolesports_livestats",
        "endpoint": "GET https://feed.lolesports.com/livestats/v1/window/{gameId}",
        "path": "gameMetadata.{blue,red}TeamMetadata.participantMetadata[].championId",
        "sample": picks,
    }


def cito_visual_fields(visual_payload: Any) -> dict[str, Any]:
    body = visual_payload if isinstance(visual_payload, dict) else {}
    blue = body.get("blueTeam") if isinstance(body.get("blueTeam"), dict) else {}
    red = body.get("redTeam") if isinstance(body.get("redTeam"), dict) else {}
    blue_gold = blue.get("gold")
    red_gold = red.get("gold")
    gold_diff = blue_gold - red_gold if isinstance(blue_gold, (int, float)) and isinstance(red_gold, (int, float)) else None
    return {
        "teamIdentity": {
            "status": "present" if blue.get("tag") and red.get("tag") else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "blueTeam.tag, redTeam.tag",
            "sample": {"blue": blue.get("tag"), "red": red.get("tag")},
        },
        "gold": {
            "status": "present" if gold_diff is not None else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "blueTeam.gold, redTeam.gold",
            "sample": {"blue": blue_gold, "red": red_gold},
        },
        "goldDiff": {
            "status": "present" if gold_diff is not None else "missing",
            "source": "derived_from_cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "blueTeam.gold - redTeam.gold",
            "sample": gold_diff,
        },
        "objectives": {
            "status": "present" if any(blue.get(k) is not None and red.get(k) is not None for k in ("dragons", "barons", "towers")) else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "blueTeam.{dragons,barons,towers}, redTeam.{dragons,barons,towers}",
            "sample": {
                "blue": {key: blue.get(key) for key in ("dragons", "barons", "towers")},
                "red": {key: red.get(key) for key in ("dragons", "barons", "towers")},
            },
        },
        "kills": {
            "status": "present" if blue.get("kills") is not None and red.get("kills") is not None else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "blueTeam.kills, redTeam.kills",
            "sample": {"blue": blue.get("kills"), "red": red.get("kills")},
        },
        "gameClock": {
            "status": "present" if body.get("gameTimeFormatted") or body.get("gameTimeSeconds") is not None else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "gameTimeFormatted, gameTimeSeconds",
            "sample": {"formatted": body.get("gameTimeFormatted"), "seconds": body.get("gameTimeSeconds")},
        },
        "gameState": {
            "status": "present" if body.get("status") else "missing",
            "source": "cito_visual_state",
            "endpoint": "GET /api/v1/lol/live/{gameId}/visual-state",
            "path": "status",
            "sample": body.get("status"),
        },
    }


def event_from_event_details(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data_event = (payload.get("data") or {}).get("event") if isinstance(payload.get("data"), dict) else None
    if isinstance(data_event, dict):
        return data_event
    event = payload.get("event")
    return event if isinstance(event, dict) else None


def reconcile_winner(event_payload: Any) -> dict[str, Any]:
    event = event_from_event_details(event_payload)
    match = (event or {}).get("match") if isinstance(event, dict) else {}
    teams = match.get("teams") if isinstance(match, dict) else []
    games = match.get("games") if isinstance(match, dict) else []
    completed_games = [game for game in games or [] if isinstance(game, dict) and game.get("state") == "completed"]
    candidates = []
    for team in teams or []:
        if not isinstance(team, dict):
            continue
        result = team.get("result") if isinstance(team.get("result"), dict) else {}
        game_wins = result.get("gameWins")
        if isinstance(game_wins, int):
            candidates.append(
                {
                    "id": str(team.get("id")),
                    "code": team.get("code"),
                    "name": team.get("name"),
                    "gameWins": game_wins,
                }
            )
    winner = None
    if len(candidates) >= 2 and completed_games:
        ordered = sorted(candidates, key=lambda item: item["gameWins"], reverse=True)
        if ordered[0]["gameWins"] > ordered[1]["gameWins"]:
            winner = ordered[0]
    return {
        "status": "present" if winner else "pending",
        "source": "lolesports_event_details",
        "endpoint": "GET https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={matchId}",
        "path": "event.match.teams[].result.gameWins with event.match.games[].state",
        "sample": winner,
        "teamResults": candidates,
        "completedGameCount": len(completed_games),
    }


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_markdown(path: Path, result: dict[str, Any]) -> str:
    lines = [
        "# CAL-59 Dual Source Field Probe",
        "",
        f"Window: `{result['startedAt']}` to `{result['endedAt']}` UTC.",
        "",
        "Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.",
        "",
        "## Target",
        "",
        f"- matchId: `{result['target']['matchId']}`",
        f"- gameId: `{result['target']['gameId']}`",
        "",
        "## Field Coverage",
        "",
        "| Field | Status | Source | Path | Sample |",
        "|---|---|---|---|---|",
    ]
    for field, item in result["fieldCoverage"].items():
        sample = json.dumps(item.get("sample"), ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{field}` | `{item.get('status')}` | `{item.get('source')}` | `{item.get('path')}` | `{sample}` |")
    lines.extend(
        [
            "",
            "## Winner Reconciliation",
            "",
            f"- status: `{result['fieldCoverage']['winner']['status']}`",
            f"- completedGameCount: `{result['fieldCoverage']['winner']['completedGameCount']}`",
            f"- teamResults: `{json.dumps(result['fieldCoverage']['winner']['teamResults'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Conclusion",
            "",
            result["conclusion"],
            "",
            f"Raw JSON: `{result['rawSamplePath']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def build_conclusion(result: dict[str, Any]) -> str:
    missing = [field for field, item in result["fieldCoverage"].items() if item.get("status") == "missing"]
    pending = [field for field, item in result["fieldCoverage"].items() if item.get("status") == "pending"]
    if missing or pending:
        return "Dual-source mapping is wired, but unresolved fields remain: " + ", ".join([*missing, *pending]) + "."
    return "Dual-source mapping resolved every tracked field, including winner reconciliation."


def run_probe(
    *,
    cito_api_key: str,
    output_dir: Path,
    target_teams: tuple[str, str],
    timeout_sec: float,
    http_get: HttpGet,
    now: Callable[[], str] = utc_now,
    match_id: str | None = None,
    game_id: str | None = None,
    winner_poll_attempts: int = 1,
    winner_poll_interval_sec: float = 0.0,
) -> dict[str, Any]:
    started_at = now()
    stamp = utc_stamp(started_at)
    cito_headers = {"x-api-key": cito_api_key}
    lol_headers = {"x-api-key": LOLESPORTS_KEY}

    match_id = normalize_cito_id(match_id)
    game_id = normalize_cito_id(game_id)

    live_payload = None
    schedule_payload = None
    if match_id:
        live_record = skipped_record("skipped_explicit_match_id")
        schedule_record = skipped_record("skipped_explicit_match_id")
    else:
        live_payload, live_record = http_get(f"{CITO_BASE_URL}/lol/live", headers=cito_headers, timeout=timeout_sec)
        target_match = discover_target_match(live_payload, target_teams)
        match_id = normalize_cito_id((target_match or {}).get("matchId") or (target_match or {}).get("id"))
        if match_id:
            schedule_record = skipped_record("skipped_live_match_found")
        else:
            schedule_payload, schedule_record = http_get(f"{CITO_BASE_URL}/lol/schedule/today", headers=cito_headers, timeout=timeout_sec)
            target_match = discover_target_match(schedule_payload, target_teams)
            match_id = normalize_cito_id((target_match or {}).get("matchId") or (target_match or {}).get("id"))

    coverage_payload = None
    coverage_record = skipped_record("skipped_no_match_id")
    if game_id:
        coverage_record = skipped_record("skipped_explicit_game_id")
    elif match_id:
        coverage_payload, coverage_record = http_get(f"{CITO_BASE_URL}/lol/matches/{match_id}/coverage", headers=cito_headers, timeout=timeout_sec)
        game_id = discover_visual_game_id(coverage_payload)

    visual_payload = None
    visual_record = skipped_record("skipped_no_game_id")
    if game_id:
        visual_payload, visual_record = http_get(f"{CITO_BASE_URL}/lol/live/{game_id}/visual-state", headers=cito_headers, timeout=timeout_sec)

    event_details_payload = None
    event_details_record = skipped_record("skipped_no_match_id")
    event_details_poll_records: list[dict[str, Any]] = []
    winner_coverage = reconcile_winner(None)
    if match_id:
        attempts = max(1, winner_poll_attempts)
        for attempt in range(1, attempts + 1):
            event_details_payload, event_details_record = http_get(LOLESPORTS_EVENT_DETAILS_URL.format(match_id=match_id), headers=lol_headers, timeout=timeout_sec)
            winner_coverage = reconcile_winner(event_details_payload)
            event_details_poll_records.append({**event_details_record, "attempt": attempt, "winnerStatus": winner_coverage["status"]})
            if winner_coverage["status"] == "present":
                break
            if attempt < attempts and winner_poll_interval_sec > 0:
                time.sleep(winner_poll_interval_sec)

    window_payload = None
    window_record = skipped_record("skipped_no_game_id")
    if game_id:
        window_payload, window_record = http_get(LOLESPORTS_WINDOW_URL.format(game_id=game_id), timeout=timeout_sec)

    field_coverage = cito_visual_fields(visual_payload)
    field_coverage["draftPicks"] = extract_draft_picks(window_payload)
    field_coverage["winner"] = winner_coverage

    ended_at = now()
    result = {
        "script": "scripts/field_source_map_probe.py",
        "scope": "CAL-59 dual-source field source map probe",
        "startedAt": started_at,
        "endedAt": ended_at,
        "target": {"teams": list(target_teams), "matchId": match_id, "gameId": game_id},
        "requests": {
            "citoLive": live_record,
            "citoScheduleToday": schedule_record,
            "citoCoverage": coverage_record,
            "citoVisualState": visual_record,
            "lolesportsEventDetails": event_details_record,
            "lolesportsEventDetailsPolls": event_details_poll_records,
            "lolesportsWindow": window_record,
        },
        "raw": {
            "citoLive": live_payload,
            "citoScheduleToday": schedule_payload,
            "citoCoverage": coverage_payload,
            "citoVisualState": visual_payload,
            "lolesportsEventDetails": event_details_payload,
            "lolesportsWindow": window_payload,
        },
        "fieldCoverage": field_coverage,
        "boundaryFindings": ["read_only_get_requests_only", "no_wallet", "no_private_key", "no_trade_execution", "no_strategy_or_signal"],
    }
    result["conclusion"] = build_conclusion(result)
    raw_path = output_dir / f"field-source-map-probe-{stamp}.json"
    result["rawSamplePath"] = str(raw_path)
    write_json(raw_path, result)
    report_path = output_dir / f"field-source-map-probe-{stamp}.md"
    result["reportPath"] = write_markdown(report_path, result)
    write_json(raw_path, result)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/source-spike")
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--target-team", action="append", dest="target_teams")
    parser.add_argument("--match-id")
    parser.add_argument("--game-id")
    parser.add_argument("--winner-poll-attempts", type=int, default=1)
    parser.add_argument("--winner-poll-interval-sec", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    key_result = load_cito_api_key(Path(".env"))
    cito_api_key = os.environ.get("CITO_API_KEY")
    if not cito_api_key:
        print(json.dumps({"error": "missing_CITO_API_KEY", "keySource": key_result.source}, indent=2), file=sys.stderr)
        return 2
    target_teams = tuple(args.target_teams or DEFAULT_TARGET_TEAMS)
    if len(target_teams) != 2:
        print("--target-team must be provided exactly twice when used", file=sys.stderr)
        return 2
    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-field-source-map-probe/0.1"})

    def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 20.0):
        return real_http_get(session, url, headers=headers, timeout=timeout)

    result = run_probe(
        cito_api_key=cito_api_key,
        output_dir=Path(args.output_dir),
        target_teams=(str(target_teams[0]), str(target_teams[1])),
        timeout_sec=args.timeout_sec,
        http_get=http_get,
        match_id=args.match_id,
        game_id=args.game_id,
        winner_poll_attempts=args.winner_poll_attempts,
        winner_poll_interval_sec=args.winner_poll_interval_sec,
    )
    print(json.dumps({k: result[k] for k in ("target", "fieldCoverage", "conclusion", "rawSamplePath", "reportPath")}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
