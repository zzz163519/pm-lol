#!/usr/bin/env python3
"""Read-only LoLEsports livestats field probe for CAL-59 T1 vs G2."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


LOLESPORTS_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
EVENT_DETAILS_URL = "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={match_id}"
SCHEDULE_URL = "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US"
LIVE_WINDOW_URL = "https://feed.lolesports.com/livestats/v1/window/{game_id}"
LIVE_DETAILS_URL = "https://feed.lolesports.com/livestats/v1/details/{game_id}"
DEFAULT_TARGET_TEAMS = ("T1", "G2")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_stamp(value: str) -> str:
    return re.sub(r"[^0-9TZ]", "", value)


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
    if left_dt is None or right_dt is None:
        return None
    return round(left_dt.timestamp() - right_dt.timestamp(), 3)


def classify_error_message(message: str) -> str:
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "json" in lower or "parse" in lower:
        return "parse_error"
    if "ssl" in lower or "connection" in lower:
        return "network_error"
    return "request_error"


def fetch(session: requests.Session, url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0) -> tuple[Any | None, dict[str, Any]]:
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
            "hasBody": False,
            "errorClass": classify_error_message(str(exc)),
            "error": str(exc),
        }

    record = {
        "observedAt": observed_at,
        "elapsedSec": round(time.monotonic() - started, 3),
        "url": url,
        "ok": 200 <= response.status_code < 300 and bool(response.content),
        "statusCode": response.status_code,
        "hasBody": bool(response.content),
        "errorClass": "empty_body" if response.status_code == 204 or not response.content else ("http_error" if response.status_code >= 400 else None),
        "error": None,
    }
    if response.status_code == 204 or not response.content:
        return None, record
    if response.status_code >= 400:
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


def find_target_event(payload: Any, target_teams: tuple[str, str]) -> dict[str, Any] | None:
    targets = tuple(team.lower() for team in target_teams)
    if isinstance(payload, dict):
        event = payload.get("event") if "event" in payload else payload
        match = event.get("match") if isinstance(event, dict) else None
        if isinstance(match, dict) and all(team in text_blob(match) for team in targets):
            return event
        for child in payload.values():
            found = find_target_event(child, target_teams)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = find_target_event(child, target_teams)
            if found:
                return found
    return None


def event_summary(event: dict[str, Any] | None) -> dict[str, Any]:
    event = event or {}
    match = event.get("match") or {}
    teams = match.get("teams") or []
    games = match.get("games") or []
    return {
        "eventId": str(event.get("id") or match.get("id")) if event.get("id") or match.get("id") else None,
        "matchId": str(match.get("id") or event.get("id")) if match.get("id") or event.get("id") else None,
        "state": event.get("state"),
        "startTime": event.get("startTime"),
        "league": ((event.get("league") or {}).get("name") or (event.get("league") or {}).get("slug")),
        "teams": [{"id": str(team.get("id")), "name": team.get("name"), "code": team.get("code")} for team in teams if isinstance(team, dict)],
        "games": [
            {
                "id": str(game.get("id")),
                "number": game.get("number"),
                "state": game.get("state"),
                "teams": game.get("teams") or [],
            }
            for game in games
            if isinstance(game, dict) and game.get("id")
        ],
    }


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


def final_picks(payload: Any) -> dict[str, list[str]]:
    metadata = (payload or {}).get("gameMetadata") if isinstance(payload, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    picks: dict[str, list[str]] = {"blue": [], "red": []}
    for side, key in (("blue", "blueTeamMetadata"), ("red", "redTeamMetadata")):
        team = metadata.get(key)
        if not isinstance(team, dict):
            continue
        for participant in team.get("participantMetadata") or []:
            if isinstance(participant, dict) and participant.get("championId"):
                picks[side].append(str(participant["championId"]))
    return picks


def side_sample(team: Any) -> dict[str, Any]:
    if not isinstance(team, dict):
        return {"gold": None, "kills": None, "towers": None, "dragons": None, "barons": None, "inhibitors": None}
    return {
        "gold": team.get("totalGold"),
        "kills": team.get("totalKills"),
        "towers": team.get("towers"),
        "dragons": team.get("dragons"),
        "barons": team.get("barons"),
        "inhibitors": team.get("inhibitors"),
    }


def field_coverage(window_payload: Any, details_payload: Any, event: dict[str, Any] | None) -> dict[str, Any]:
    frame = sample_frame(window_payload) or sample_frame(details_payload)
    blue = frame.get("blueTeam") if isinstance(frame, dict) else None
    red = frame.get("redTeam") if isinstance(frame, dict) else None
    picks = final_picks(window_payload) or final_picks(details_payload)
    blue_side = side_sample(blue)
    red_side = side_sample(red)
    blue_gold = blue_side.get("gold")
    red_gold = red_side.get("gold")
    gold_diff = blue_gold - red_gold if isinstance(blue_gold, (int, float)) and isinstance(red_gold, (int, float)) else None
    summary = event_summary(event)
    return {
        "teamIdentity": {"status": "present" if len(summary["teams"]) >= 2 else "missing", "sample": summary["teams"][:2]},
        "gold": {"status": "present" if gold_diff is not None else "missing", "sample": {"blue": blue_gold, "red": red_gold}, "goldDiff": gold_diff},
        "objectives": {
            "status": "present" if any(blue_side.get(key) is not None and red_side.get(key) is not None for key in ("towers", "dragons", "barons", "inhibitors")) else "missing",
            "sample": {"blue": {k: blue_side.get(k) for k in ("towers", "dragons", "barons", "inhibitors")}, "red": {k: red_side.get(k) for k in ("towers", "dragons", "barons", "inhibitors")}},
        },
        "kills": {"status": "present" if blue_side.get("kills") is not None and red_side.get("kills") is not None else "missing", "sample": {"blue": blue_side.get("kills"), "red": red_side.get("kills")}},
        "draftPicks": {"status": "present" if len(picks["blue"]) + len(picks["red"]) >= 10 else "missing", "sample": picks},
        "gameState": {"status": "present" if isinstance(frame, dict) and frame.get("gameState") else ("present" if summary.get("state") else "missing"), "sample": frame.get("gameState") if isinstance(frame, dict) else summary.get("state")},
        "gameClock": {"status": "derived_from_frame_timestamp" if isinstance(frame, dict) and frame.get("rfc460Timestamp") else "missing", "sample": frame.get("rfc460Timestamp") if isinstance(frame, dict) else None},
        "winner": {"status": "present" if any(game.get("state") == "completed" for game in summary["games"]) else "missing", "sample": "not_exposed_in_livestats_frame"},
    }


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_markdown(path: Path, result: dict[str, Any]) -> str:
    lines = [
        "# CAL-59 LoLEsports Livestats Field Probe",
        "",
        f"Window: `{result['startedAt']}` to `{result['endedAt']}` UTC.",
        "",
        "Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.",
        "",
        "## Target",
        "",
        f"- matchId: `{result['target']['matchId']}`",
        f"- gameId: `{result['target']['gameId']}`",
        f"- event state: `{result['target']['eventState']}`",
        "",
        "## Endpoint Status",
        "",
        f"- schedule: `{result['requests']['schedule']['statusCode']}` / `{result['requests']['schedule']['errorClass']}`",
        f"- eventDetails: `{result['requests']['eventDetails']['statusCode']}` / `{result['requests']['eventDetails']['errorClass']}`",
        f"- window: `{result['requests']['window']['statusCode']}` / `{result['requests']['window']['errorClass']}`",
        f"- details: `{result['requests']['details']['statusCode']}` / `{result['requests']['details']['errorClass']}`",
        "",
        "## Freshness",
        "",
        f"- frame timestamp: `{result['freshness']['frameTimestamp']}`",
        f"- frame age: `{result['freshness']['frameAgeSec']}` seconds",
        f"- freshness threshold: `{result['freshness']['freshnessThresholdSec']}` seconds",
        "",
        "## Field Coverage",
        "",
        "| Field | Status | Sample |",
        "|---|---|---|",
    ]
    for name, item in result["fieldCoverage"].items():
        sample = json.dumps(item.get("sample"), ensure_ascii=False, sort_keys=True)
        extra = f"; goldDiff={item['goldDiff']}" if name == "gold" else ""
        lines.append(f"| `{name}` | `{item.get('status')}` | `{sample}{extra}` |")
    lines.extend(["", "## Conclusion", "", result["conclusion"], "", f"Raw JSON: `{result['rawSamplePath']}`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def build_conclusion(result: dict[str, Any]) -> str:
    window = result["requests"]["window"]
    details = result["requests"]["details"]
    if window.get("statusCode") == 204 and details.get("statusCode") == 204:
        return "LoLEsports schedule/eventDetails can map T1 vs G2, but livestats window/details returned 204/no body in this run, so it cannot yet supplement Cito's missing live fields."
    missing = [name for name, item in result["fieldCoverage"].items() if item.get("status") == "missing"]
    frame_age = result["freshness"].get("frameAgeSec")
    stale_note = ""
    if isinstance(frame_age, (int, float)) and frame_age > 120:
        stale_note = f" Latest livestats frame was stale at {frame_age}s old, so treat this as schema/field evidence, not fresh live state."
    if missing:
        return "LoLEsports livestats partially supplements Cito, but these fields remain missing: " + ", ".join(missing) + "." + stale_note
    return "LoLEsports livestats covers the requested fields for this sample; winner still needs postgame/event reconciliation before using as final source." + stale_note


def run_probe(*, output_dir: Path, target_teams: tuple[str, str], timeout_sec: float) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-lolesports-t1-g2-livestats-probe/0.1"})
    headers = {"x-api-key": LOLESPORTS_KEY}
    started_at = utc_now()
    stamp = utc_stamp(started_at)

    schedule_payload, schedule_record = fetch(session, SCHEDULE_URL, headers=headers, timeout=timeout_sec)
    event = find_target_event(schedule_payload, target_teams)
    summary = event_summary(event)
    event_details_payload = None
    event_details_record = {"statusCode": None, "errorClass": "skipped_no_match_id", "ok": False}
    if summary.get("matchId"):
        event_details_payload, event_details_record = fetch(session, EVENT_DETAILS_URL.format(match_id=summary["matchId"]), headers=headers, timeout=timeout_sec)
        details_event = ((event_details_payload or {}).get("data") or {}).get("event") if isinstance(event_details_payload, dict) else None
        if isinstance(details_event, dict):
            event = details_event
            summary = event_summary(event)

    game = next((candidate for candidate in summary.get("games") or [] if candidate.get("number") == 1), None)
    game_id = str(game.get("id")) if isinstance(game, dict) and game.get("id") else None
    window_payload = None
    details_payload = None
    window_record = {"statusCode": None, "errorClass": "skipped_no_game_id", "ok": False}
    details_record = {"statusCode": None, "errorClass": "skipped_no_game_id", "ok": False}
    if game_id:
        window_payload, window_record = fetch(session, LIVE_WINDOW_URL.format(game_id=game_id), timeout=timeout_sec)
        details_payload, details_record = fetch(session, LIVE_DETAILS_URL.format(game_id=game_id), timeout=timeout_sec)

    coverage = field_coverage(window_payload, details_payload, event)
    frame = sample_frame(window_payload) or sample_frame(details_payload)
    frame_ts = frame.get("rfc460Timestamp") if isinstance(frame, dict) else None
    ended_at = utc_now()
    result = {
        "script": "scripts/lolesports_t1_g2_livestats_probe.py",
        "scope": "CAL-59 LoLEsports livestats T1 vs G2 field supplement probe",
        "startedAt": started_at,
        "endedAt": ended_at,
        "target": {"teams": list(target_teams), "matchId": summary.get("matchId"), "gameId": game_id, "eventState": summary.get("state"), "startTime": summary.get("startTime"), "event": summary},
        "requests": {"schedule": schedule_record, "eventDetails": event_details_record, "window": window_record, "details": details_record},
        "raw": {"schedule": schedule_payload, "eventDetails": event_details_payload, "window": window_payload, "details": details_payload},
        "fieldCoverage": coverage,
        "freshness": {
            "frameTimestamp": frame_ts,
            "frameAgeSec": seconds_between(ended_at, str(frame_ts) if frame_ts else None),
            "freshnessThresholdSec": 120,
        },
        "boundaryFindings": ["read_only_get_requests_only", "no_wallet", "no_private_key", "no_trade_execution", "no_strategy_or_signal"],
    }
    result["conclusion"] = build_conclusion(result)
    raw_path = output_dir / f"lolesports-t1-g2-livestats-probe-{stamp}.json"
    result["rawSamplePath"] = str(raw_path)
    write_json(raw_path, result)
    report_path = output_dir / f"lolesports-t1-g2-livestats-probe-{stamp}.md"
    result["reportPath"] = write_markdown(report_path, result)
    write_json(raw_path, result)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/source-spike")
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--target-team", action="append", dest="target_teams")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    target_teams = tuple(args.target_teams or DEFAULT_TARGET_TEAMS)
    if len(target_teams) != 2:
        print("--target-team must be provided exactly twice when used", file=sys.stderr)
        return 2
    result = run_probe(output_dir=Path(args.output_dir), target_teams=(str(target_teams[0]), str(target_teams[1])), timeout_sec=args.timeout_sec)
    print(json.dumps({k: result[k] for k in ("target", "requests", "fieldCoverage", "conclusion", "rawSamplePath", "reportPath")}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
