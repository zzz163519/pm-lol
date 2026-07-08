#!/usr/bin/env python3
"""Read-only Cito field completeness probe for CAL-59 T1 vs G2."""

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
DEFAULT_TARGET_TEAMS = ("T1", "G2")


class ApiKeyLoadResult(NamedTuple):
    present: bool
    source: str | None
    length: int


HttpGet = Callable[..., tuple[Any | None, dict[str, Any]]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_stamp(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(".", "").replace("Z", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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


def current_cito_api_key() -> str | None:
    return os.environ.get("CITO_API_KEY") or None


def classify_error_message(message: str) -> str:
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "json" in lower or "parse" in lower:
        return "parse_error"
    if "ssl" in lower or "connection" in lower:
        return "network_error"
    return "request_error"


def real_http_get(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> tuple[Any | None, dict[str, Any]]:
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
            "errorClass": classify_error_message(str(exc)),
            "error": str(exc),
        }

    record = {
        "observedAt": observed_at,
        "elapsedSec": round(time.monotonic() - started, 3),
        "url": url,
        "ok": 200 <= response.status_code < 300,
        "statusCode": response.status_code,
        "errorClass": "rate_limited" if response.status_code == 429 else ("http_error" if response.status_code >= 400 else None),
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


def find_match_candidates(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            keys = set(value)
            id_like = {"id", "matchId", "officialEventId", "gameId", "currentGameId"} & keys
            match_like = {"teams", "teamA", "teamB", "startTime", "scheduledStartTime", "state", "status"} & keys
            if id_like and match_like:
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return found


def find_target_match(payload: Any, target_teams: tuple[str, str]) -> dict[str, Any] | None:
    targets = tuple(team.lower() for team in target_teams)
    for match in find_match_candidates(payload):
        blob = text_blob(match)
        if all(target in blob for target in targets):
            return match
    return None


def find_first_value(value: Any, names: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in names and child not in (None, [], {}):
                return child
        for child in value.values():
            found = find_first_value(child, names)
            if found not in (None, [], {}):
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first_value(child, names)
            if found not in (None, [], {}):
                return found
    return None


def contains_key_name(value: Any, names: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if any(name in key_lower for name in names) and child not in (None, [], {}):
                return True
            if contains_key_name(child, names):
                return True
    elif isinstance(value, list):
        return any(contains_key_name(child, names) for child in value)
    return False


def first_number(*values: Any) -> int | float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def team_name(team: Any) -> str | None:
    if not isinstance(team, dict):
        return None
    return first_text(team.get("tag"), team.get("code"), team.get("shortName"), team.get("name"))


def team_side_summary(team: Any) -> dict[str, Any]:
    if not isinstance(team, dict):
        return {"name": None, "gold": None, "kills": None, "dragons": None, "barons": None, "towers": None, "picks": None}
    picks = (
        team.get("picks")
        or team.get("champions")
        or team.get("draft")
        or team.get("finalPicks")
        or team.get("players")
    )
    return {
        "name": team_name(team),
        "gold": first_number(team.get("gold"), team.get("totalGold")),
        "kills": first_number(team.get("kills")),
        "dragons": first_number(team.get("dragons"), team.get("dragonKills")),
        "barons": first_number(team.get("barons"), team.get("baronKills")),
        "towers": first_number(team.get("towers"), team.get("towerKills")),
        "picks": picks if picks not in (None, [], {}) else None,
    }


def visual_teams(payload: Any) -> tuple[Any, Any]:
    if not isinstance(payload, dict):
        return None, None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    blue = payload.get("blueTeam") or data.get("blueTeam")
    red = payload.get("redTeam") or data.get("redTeam")
    if blue or red:
        return blue, red
    teams = payload.get("teams") or data.get("teams")
    if isinstance(teams, list) and len(teams) >= 2:
        return teams[0], teams[1]
    return None, None


def field_status(present: bool, sample: Any = None) -> dict[str, Any]:
    return {"status": "present" if present else "missing", "sample": sample}


def summarize_visual_state_fields(payload: Any) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    blue_raw, red_raw = visual_teams(body)
    blue = team_side_summary(blue_raw)
    red = team_side_summary(red_raw)
    blue_gold = blue.get("gold")
    red_gold = red.get("gold")
    gold_diff = None
    if isinstance(blue_gold, (int, float)) and isinstance(red_gold, (int, float)):
        gold_diff = blue_gold - red_gold

    game_clock = first_text(body.get("gameTimeFormatted"), data.get("gameTimeFormatted"))
    game_clock = game_clock or first_number(body.get("gameTimeSeconds"), body.get("gameTime"), data.get("gameTimeSeconds"))
    game_state = first_text(body.get("gameState"), body.get("status"), data.get("gameState"), data.get("status"))
    winner = find_first_value(body, ("winner", "winningteam", "winning_team"))
    picks_present = blue.get("picks") is not None or red.get("picks") is not None or contains_key_name(body, ("pick", "champion"))

    objectives_sample = {
        "blue": {key: blue.get(key) for key in ("dragons", "barons", "towers")},
        "red": {key: red.get(key) for key in ("dragons", "barons", "towers")},
    }
    objectives_present = any(value is not None for side in objectives_sample.values() for value in side.values())

    return {
        "teamIdentity": field_status(bool(blue.get("name") and red.get("name")), {"blue": blue.get("name"), "red": red.get("name")}),
        "gold": {**field_status(blue_gold is not None and red_gold is not None, {"blue": blue_gold, "red": red_gold}), "goldDiff": gold_diff},
        "objectives": field_status(objectives_present, objectives_sample),
        "kills": field_status(blue.get("kills") is not None and red.get("kills") is not None, {"blue": blue.get("kills"), "red": red.get("kills")}),
        "draftPicks": field_status(picks_present, {"blue": blue.get("picks"), "red": red.get("picks")}),
        "gameState": field_status(game_state is not None, game_state),
        "gameClock": field_status(game_clock is not None, game_clock),
        "winner": field_status(winner not in (None, [], {}), winner),
    }


def discover_game_id(payload: Any, target_teams: tuple[str, str] = DEFAULT_TARGET_TEAMS) -> str | None:
    if isinstance(payload, dict):
        if all(team.lower() in text_blob(payload) for team in target_teams):
            for key in ("gameId", "currentGameId", "matchId", "id"):
                value = payload.get(key)
                if value:
                    return str(value)
        for key in ("game", "match", "data", "matches", "live", "coverage"):
            value = discover_game_id(payload.get(key), target_teams)
            if value:
                return value
        for child in payload.values():
            value = discover_game_id(child, target_teams)
            if value:
                return value
    elif isinstance(payload, list):
        for item in payload:
            value = discover_game_id(item, target_teams)
            if value:
                return value
    return None


def summarize_request_frequency(records: list[dict[str, Any]]) -> dict[str, Any]:
    cito_records = [record for record in records if "api.citoapi.com" in str(record.get("url") or "")]
    times = [parse_time(record.get("observedAt")) for record in cito_records]
    times = [value for value in times if value is not None]
    intervals = [round((right - left).total_seconds(), 3) for left, right in zip(times, times[1:])]
    started = min(times).isoformat().replace("+00:00", "Z") if times else None
    ended = max(times).isoformat().replace("+00:00", "Z") if times else None
    elapsed = (max(times) - min(times)).total_seconds() if len(times) >= 2 else 0
    max_requests_per_minute = None
    if cito_records:
        denominator = max(elapsed, 60.0)
        max_requests_per_minute = round(len(cito_records) / denominator * 60, 3)
    return {
        "citoRequestCount": len(cito_records),
        "status429Count": sum(1 for record in cito_records if record.get("statusCode") == 429),
        "minIntervalSec": min(intervals) if intervals else None,
        "maxIntervalSec": max(intervals) if intervals else None,
        "maxRequestsPerMinuteObserved": max_requests_per_minute,
        "windowStartedAt": started,
        "windowEndedAt": ended,
        "limitPolicy": "poll_interval_sec>=3 and observed_request_rate<=60_per_minute",
    }


def rate_limited(record: dict[str, Any] | None) -> bool:
    return bool(record and record.get("statusCode") == 429)


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_markdown(path: Path, result: dict[str, Any]) -> str:
    fields = result["fieldCoverage"]
    frequency = result["requestFrequency"]
    lines = [
        "# CAL-59 Cito T1 vs G2 Field Completeness Probe",
        "",
        f"Window: `{result['startedAt']}` to `{result['endedAt']}` UTC.",
        "",
        "Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.",
        "",
        "## IDs",
        "",
        f"- schedule matchId: `{result['target']['scheduleMatchId']}`",
        f"- live/discovered gameId: `{result['target']['gameId']}`",
        f"- schedule target found: `{result['target']['scheduleTargetFound']}`",
        "",
        "## Request Frequency",
        "",
        f"- Cito requests: `{frequency['citoRequestCount']}`",
        f"- 429 count: `{frequency['status429Count']}`",
        f"- min interval: `{frequency['minIntervalSec']}` seconds",
        f"- max observed request rate: `{frequency['maxRequestsPerMinuteObserved']}` requests/minute",
        "",
        "## Field Coverage",
        "",
        "| Field | Status | Sample |",
        "|---|---|---|",
    ]
    for name, item in fields.items():
        sample = json.dumps(item.get("sample"), ensure_ascii=False, sort_keys=True)
        extra = f"; goldDiff={item['goldDiff']}" if name == "gold" else ""
        lines.append(f"| `{name}` | `{item.get('status')}` | `{sample}{extra}` |")
    lines.extend(
        [
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
    if result["requestFrequency"]["status429Count"]:
        return "Blocked for Phase 1 use: Cito returned 429 during this probe, so the polling plan is not rate-limit clean."
    if not result["target"]["gameId"]:
        return "Incomplete: T1 vs G2 was not present in `/lol/live` during this run, so live/visual-state field completeness could not be proven yet."
    statuses = {key: value["status"] for key, value in result["fieldCoverage"].items()}
    missing = [key for key, status in statuses.items() if status != "present"]
    if missing:
        return "Partial: Cito returned a live candidate, but these requested fields were missing in visual-state: " + ", ".join(missing) + "."
    return "Field-complete for the sampled visual-state payload: all requested identity, gold, objectives, kills, draft/picks, game clock/state, and winner fields were present."


def run_probe(
    *,
    cito_api_key: str,
    output_dir: Path,
    target_teams: tuple[str, str],
    duration_sec: int,
    poll_interval_sec: int,
    http_get: HttpGet,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    if poll_interval_sec < 3:
        raise ValueError("poll_interval_sec must be >= 3 to leave margin under Cito 60/min limit")

    started_at = now()
    stamp = utc_stamp(started_at)
    headers = {"x-api-key": cito_api_key}
    request_records: list[dict[str, Any]] = []

    schedule_payload, schedule_record = http_get(f"{CITO_BASE_URL}/lol/schedule/today", headers=headers)
    request_records.append(schedule_record)
    target_match = find_target_match(schedule_payload, target_teams)
    schedule_match_id = None
    schedule_game_id = None
    if isinstance(target_match, dict):
        schedule_match_id = target_match.get("id") or target_match.get("matchId") or target_match.get("officialEventId")
        schedule_game_id = target_match.get("gameId") or target_match.get("currentGameId")

    iterations = []
    visual_payload = None
    game_id = str(schedule_game_id) if schedule_game_id else None
    deadline = time.monotonic() + duration_sec
    iteration = 0
    while not rate_limited(schedule_record):
        iteration += 1
        live_payload, live_record = http_get(f"{CITO_BASE_URL}/lol/live", headers=headers)
        request_records.append(live_record)
        discovered_game_id = discover_game_id(live_payload, target_teams)
        if discovered_game_id:
            game_id = discovered_game_id

        visual_record = None
        current_visual_payload = None
        if game_id:
            current_visual_payload, visual_record = http_get(f"{CITO_BASE_URL}/lol/live/{game_id}/visual-state", headers=headers)
            request_records.append(visual_record)
            visual_payload = current_visual_payload

        iterations.append(
            {
                "iteration": iteration,
                "observedAt": now(),
                "live": {"request": live_record, "body": live_payload},
                "visualState": {"request": visual_record, "body": current_visual_payload},
                "gameId": game_id,
            }
        )

        if rate_limited(live_record) or rate_limited(visual_record):
            break
        if time.monotonic() >= deadline:
            break
        sleep(poll_interval_sec)

    field_coverage = summarize_visual_state_fields(visual_payload)
    ended_at = now()
    result = {
        "script": "scripts/cito_t1_g2_field_probe.py",
        "scope": "CAL-59 Cito T1 vs G2 field completeness probe",
        "startedAt": started_at,
        "endedAt": ended_at,
        "target": {
            "teams": list(target_teams),
            "scheduleTargetFound": target_match is not None,
            "scheduleMatchId": str(schedule_match_id) if schedule_match_id else None,
            "scheduleGameId": str(schedule_game_id) if schedule_game_id else None,
            "gameId": game_id,
        },
        "polling": {
            "durationSecRequested": duration_sec,
            "pollIntervalSec": poll_interval_sec,
            "iterations": len(iterations),
        },
        "scheduleToday": {"request": schedule_record, "targetMatch": target_match, "body": schedule_payload},
        "iterations": iterations,
        "fieldCoverage": field_coverage,
        "requestFrequency": summarize_request_frequency(request_records),
        "boundaryFindings": [
            "read_only_get_requests_only",
            "no_wallet",
            "no_private_key",
            "no_trade_execution",
            "no_strategy_or_signal",
        ],
    }
    result["conclusion"] = build_conclusion(result)
    raw_path = output_dir / f"cito-t1-g2-field-probe-{stamp}.json"
    result["rawSamplePath"] = str(raw_path)
    write_json(raw_path, result)
    report_path = output_dir / f"cito-t1-g2-field-probe-{stamp}.md"
    result["reportPath"] = write_markdown(report_path, result)
    write_json(raw_path, result)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/source-spike")
    parser.add_argument("--duration-sec", type=int, default=120)
    parser.add_argument("--poll-interval-sec", type=int, default=5)
    parser.add_argument("--target-team", action="append", dest="target_teams")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    key_result = load_cito_api_key(Path(".env"))
    api_key = current_cito_api_key()
    if not api_key:
        result = {
            "script": "scripts/cito_t1_g2_field_probe.py",
            "observedAt": utc_now(),
            "overallStatus": "blocked_missing_cito_api_key",
            "auth": {"apiKeyPresent": key_result.present, "apiKeyLength": key_result.length, "source": key_result.source},
        }
        write_json(Path(args.output_dir) / "cito-t1-g2-field-probe-missing-key.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    target_teams = tuple(args.target_teams or DEFAULT_TARGET_TEAMS)
    if len(target_teams) != 2:
        print("--target-team must be provided exactly twice when used", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-cito-t1-g2-field-probe/0.1"})

    def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 20.0):
        return real_http_get(session, url, headers=headers, timeout=timeout)

    result = run_probe(
        cito_api_key=api_key,
        output_dir=Path(args.output_dir),
        target_teams=(str(target_teams[0]), str(target_teams[1])),
        duration_sec=args.duration_sec,
        poll_interval_sec=args.poll_interval_sec,
        http_get=http_get,
    )
    print(json.dumps({k: result[k] for k in ("target", "fieldCoverage", "requestFrequency", "conclusion", "rawSamplePath", "reportPath")}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
