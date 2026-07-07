#!/usr/bin/env python3
"""Read-only LYON vs FURIA LoLEsports/Polymarket live watcher smoke."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests


LOLESPORTS_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
MATCH_ID = "115570934355614533"
EVENT_SLUG = "lol-ly-fur-2026-07-03"
GAME_IDS = {
    1: "115570934355614534",
    2: "115570934355614535",
    3: "115570934355614536",
    4: "115570934355614537",
    5: "115570934355614538",
}
GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_BOOK_URL = "https://clob.polymarket.com/book?token_id={token_id}"
LOLESPORTS_EVENT_URL = (
    "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={match_id}"
)
LOLESPORTS_SCHEDULE_URL = "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US"
LIVE_WINDOW_URL = "https://feed.lolesports.com/livestats/v1/window/{game_id}"
LIVE_DETAILS_URL = "https://feed.lolesports.com/livestats/v1/details/{game_id}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_error_message(message: str) -> str:
    lower = message.lower()
    if "ssl" in lower or "eof occurred" in lower or "connection closed" in lower:
        return "ssl_error"
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "json" in lower or "parse" in lower:
        return "parse_error"
    return "network_error"


def proxy_env() -> dict[str, bool]:
    return {
        key: bool(os.environ.get(key))
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
    }


def fetch(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    expect_json: bool = True,
    timeout: float = 10.0,
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
            "hasBody": False,
            "errorClass": classify_error_message(str(exc)),
            "error": str(exc),
        }

    has_body = bool(response.content)
    record = {
        "observedAt": observed_at,
        "url": url,
        "ok": 200 <= response.status_code < 300,
        "statusCode": response.status_code,
        "hasBody": has_body,
        "errorClass": "http_error" if response.status_code >= 400 else None,
        "error": None,
    }
    if response.status_code == 204 or not has_body:
        return None, record
    if expect_json:
        try:
            return response.json(), record
        except ValueError as exc:
            record["ok"] = False
            record["errorClass"] = "parse_error"
            record["error"] = str(exc)
            return None, record
    return response.text, record


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def prices(levels: list[dict[str, Any]]) -> list[float]:
    values = []
    for level in levels:
        try:
            values.append(float(level.get("price")))
        except (TypeError, ValueError):
            pass
    return values


def summarize_orderbook(market: dict[str, Any], token_id: str, outcome: str, record: dict[str, Any], book: dict[str, Any] | None) -> dict[str, Any]:
    bids = book.get("bids") if isinstance(book, dict) else []
    asks = book.get("asks") if isinstance(book, dict) else []
    bid_prices = prices(bids or [])
    ask_prices = prices(asks or [])
    source_ts = book.get("timestamp") if isinstance(book, dict) else None
    observed_dt = parse_time(record.get("observedAt"))
    source_latency = None
    if source_ts and observed_dt:
        try:
            source_latency = observed_dt.timestamp() - (float(source_ts) / 1000.0)
        except (TypeError, ValueError):
            source_latency = None
    return {
        "marketSlug": market.get("marketSlug"),
        "gameNumber": market.get("gameNumber"),
        "conditionId": market.get("conditionId"),
        "tokenId": token_id,
        "outcome": outcome,
        "statusCode": record.get("statusCode"),
        "hasBody": record.get("hasBody"),
        "bidCount": len(bids or []),
        "askCount": len(asks or []),
        "bestBid": max(bid_prices) if bid_prices else None,
        "bestAsk": min(ask_prices) if ask_prices else None,
        "sourceTimestamp": source_ts,
        "sourceLatencySec": source_latency,
        "errorClass": record.get("errorClass"),
        "error": record.get("error"),
    }


def extract_game_number(market: dict[str, Any]) -> int | None:
    text = " ".join(str(market.get(key) or "") for key in ("slug", "question", "title"))
    match = re.search(r"game[-\s]?([1-5]).*winner", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def discover_polymarket_markets(session: requests.Session) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    payload, record = fetch(session, GAMMA_EVENT_URL.format(slug=EVENT_SLUG), timeout=15.0)
    if not record.get("ok") or not isinstance(payload, dict):
        warnings.append(f"Polymarket Gamma event lookup failed: {record.get('errorClass') or record.get('statusCode')}")
        return [], warnings

    markets = []
    for market in payload.get("markets") or []:
        game_number = extract_game_number(market)
        if game_number not in (1, 2):
            continue
        outcomes = parse_jsonish(market.get("outcomes"))
        token_ids = parse_jsonish(market.get("clobTokenIds"))
        if not isinstance(outcomes, list) or not isinstance(token_ids, list):
            continue
        markets.append(
            {
                "marketSlug": market.get("slug"),
                "question": market.get("question") or market.get("title"),
                "gameNumber": game_number,
                "conditionId": market.get("conditionId"),
                "outcomes": outcomes,
                "clobTokenIds": token_ids,
            }
        )
    if not markets:
        warnings.append("No Game 1/2 Winner markets discovered for LYON vs FURIA.")
    return sorted(markets, key=lambda item: item["gameNumber"]), warnings


def find_schedule_event(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        event = payload.get("event") if "event" in payload else payload
        match = event.get("match") if isinstance(event, dict) else None
        if isinstance(match, dict) and str(match.get("id")) == MATCH_ID:
            return event
        for value in payload.values():
            found = find_schedule_event(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_schedule_event(value)
            if found:
                return found
    return None


def summarize_event_details(payload: dict[str, Any] | None, schedule_event: dict[str, Any] | None, event_record: dict[str, Any], schedule_record: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]], list[str]]:
    warnings = []
    event = ((payload or {}).get("data") or {}).get("event") or {}
    match = event.get("match") or {}
    teams = match.get("teams") or []
    games = match.get("games") or []
    if not event and schedule_event:
        event = schedule_event
        match = event.get("match") or {}
        teams = match.get("teams") or teams
    event_state = event.get("state") or (schedule_event or {}).get("state")
    if event_record.get("errorClass"):
        warnings.append(f"eventDetails error: {event_record.get('errorClass')}")
    if schedule_record.get("errorClass"):
        warnings.append(f"schedule error: {schedule_record.get('errorClass')}")
    team_by_id = {str(team.get("id")): {"id": str(team.get("id")), "name": team.get("name"), "code": team.get("code")} for team in teams}
    summarized_games = []
    for number, game_id in GAME_IDS.items():
        game_payload = next((game for game in games if str(game.get("id")) == game_id), None)
        game_teams = []
        if game_payload:
            for team_side in game_payload.get("teams") or []:
                team_id = str(team_side.get("id"))
                team_info = dict(team_by_id.get(team_id, {"id": team_id}))
                team_info["side"] = team_side.get("side")
                game_teams.append(team_info)
        summarized_games.append(
            {
                "gameId": game_id,
                "gameNumber": number,
                "state": (game_payload or {}).get("state"),
                "teams": game_teams,
            }
        )
    return event_state, summarized_games, warnings


def summarize_livestats(game_id: str, game_number: int, record: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    sample = None
    metadata: dict[str, Any] = {}
    if isinstance(payload, dict):
        metadata = payload.get("gameMetadata") or {}
        sample = payload.get("sampleFrame")
        if sample is None and payload.get("frames"):
            sample = payload["frames"][-1]
    source_ts = sample.get("rfc460Timestamp") if isinstance(sample, dict) else None
    observed_dt = parse_time(record.get("observedAt"))
    source_dt = parse_time(source_ts)
    latency = observed_dt.timestamp() - source_dt.timestamp() if observed_dt and source_dt else None
    blue = sample.get("blueTeam") if isinstance(sample, dict) else {}
    red = sample.get("redTeam") if isinstance(sample, dict) else {}
    return {
        "gameId": game_id,
        "gameNumber": game_number,
        "statusCode": record.get("statusCode"),
        "hasBody": record.get("hasBody"),
        "gameState": sample.get("gameState") if isinstance(sample, dict) else None,
        "sourceTimestamp": source_ts,
        "sourceLatencySec": latency,
        "hasGameState": bool(isinstance(sample, dict) and sample.get("gameState")),
        "hasGold": bool(blue.get("totalGold") is not None and red.get("totalGold") is not None),
        "hasObjectives": bool(blue or red),
        "hasPicks": bool(metadata.get("blueTeamMetadata") or metadata.get("redTeamMetadata")),
        "blueGold": blue.get("totalGold") if isinstance(blue, dict) else None,
        "redGold": red.get("totalGold") if isinstance(red, dict) else None,
        "blueKills": blue.get("totalKills") if isinstance(blue, dict) else None,
        "redKills": red.get("totalKills") if isinstance(red, dict) else None,
        "errorClass": record.get("errorClass"),
        "error": record.get("error"),
    }


def collect_sample(session: requests.Session, markets: list[dict[str, Any]]) -> dict[str, Any]:
    observed_at = utc_now()
    warnings = []
    event_payload, event_record = fetch(
        session,
        LOLESPORTS_EVENT_URL.format(match_id=MATCH_ID),
        headers={"x-api-key": LOLESPORTS_KEY},
        timeout=12.0,
    )
    schedule_payload, schedule_record = fetch(
        session,
        LOLESPORTS_SCHEDULE_URL,
        headers={"x-api-key": LOLESPORTS_KEY},
        timeout=12.0,
    )
    schedule_event = find_schedule_event(schedule_payload) if isinstance(schedule_payload, dict) else None
    event_state, games, state_warnings = summarize_event_details(event_payload, schedule_event, event_record, schedule_record)
    warnings.extend(state_warnings)

    windows = []
    details = []
    for number, game_id in GAME_IDS.items():
        window_payload, window_record = fetch(session, LIVE_WINDOW_URL.format(game_id=game_id), timeout=8.0)
        details_payload, details_record = fetch(session, LIVE_DETAILS_URL.format(game_id=game_id), timeout=8.0)
        windows.append(summarize_livestats(game_id, number, window_record, window_payload))
        details.append(summarize_livestats(game_id, number, details_record, details_payload))

    orderbooks = []
    for market in markets[:2]:
        token_ids = market.get("clobTokenIds") or []
        outcomes = market.get("outcomes") or []
        if not token_ids:
            continue
        token_id = str(token_ids[0])
        outcome = str(outcomes[0]) if outcomes else "unknown"
        book_payload, book_record = fetch(session, CLOB_BOOK_URL.format(token_id=token_id), timeout=10.0)
        orderbooks.append(summarize_orderbook(market, token_id, outcome, book_record, book_payload))

    if event_state == "unstarted":
        warnings.append("LoLEsports event state is still unstarted.")
    if all(item.get("statusCode") == 204 for item in windows):
        warnings.append("All livestats window endpoints returned 204/no body.")
    if all(item.get("statusCode") == 204 for item in details):
        warnings.append("All livestats details endpoints returned 204/no body.")
    if any(book.get("statusCode") == 200 for book in orderbooks):
        warnings.append("Polymarket CLOB orderbook is readable while LoLEsports may still be unstarted/204.")

    return {
        "observedAt": observed_at,
        "matchId": MATCH_ID,
        "eventSlug": EVENT_SLUG,
        "eventState": event_state,
        "games": games,
        "livestatsWindow": windows,
        "livestatsDetails": details,
        "polymarketOrderbooks": orderbooks,
        "sourceTimestamp": None,
        "sourceLatencySec": None,
        "warnings": warnings,
    }


def write_summary(path: str, jsonl_path: str, samples: list[dict[str, Any]], started_at: str, ended_at: str) -> None:
    states = sorted({sample.get("eventState") for sample in samples})
    window_codes = {}
    detail_codes = {}
    readable_books = 0
    latency_values = []
    for sample in samples:
        for item in sample.get("livestatsWindow") or []:
            window_codes[item.get("statusCode")] = window_codes.get(item.get("statusCode"), 0) + 1
            if item.get("sourceLatencySec") is not None:
                latency_values.append(item["sourceLatencySec"])
        for item in sample.get("livestatsDetails") or []:
            detail_codes[item.get("statusCode")] = detail_codes.get(item.get("statusCode"), 0) + 1
        if any(book.get("statusCode") == 200 for book in sample.get("polymarketOrderbooks") or []):
            readable_books += 1
    can_compute_latency = bool(latency_values)
    lines = [
        "# LYON vs FURIA Live Watcher Smoke",
        "",
        f"- 采集窗口：`{started_at}` -> `{ended_at}`",
        f"- JSONL：`{jsonl_path}`",
        f"- 样本数：{len(samples)}",
        f"- LoLEsports eventState：{states}",
        f"- livestats window status 分布：{window_codes}",
        f"- livestats details status 分布：{detail_codes}",
        f"- Polymarket orderbook 可读样本数：{readable_books}/{len(samples)}",
        f"- 是否可计算 LoLEsports source latency：{can_compute_latency}",
        "",
        "## 结论",
        "",
    ]
    if not can_compute_latency:
        lines.append("- 本窗口内未拿到 LoLEsports livestats body/sourceTimestamp，不能计算 live latency。")
    if states == ["unstarted"] or "unstarted" in states:
        lines.append("- LoLEsports schedule/eventDetails 至少部分样本仍为 `unstarted`。")
    if window_codes.get(204):
        lines.append("- livestats window 存在 204/no body，不能宣称 live validation passed。")
    if readable_books:
        lines.append("- Polymarket CLOB orderbook 在采集窗口内可读。")
    lines.append("- 本次只读 watcher 不构成策略、信号、下单或 Phase 0 完成证明。")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", default="docs/source-spike/lyon-furia-live-watcher-2026-07-03.jsonl")
    parser.add_argument("--summary", default="docs/source-spike/lyon-furia-live-watcher-2026-07-03.md")
    parser.add_argument("--duration-sec", type=int, default=600)
    parser.add_argument("--interval-sec", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-live-watcher-smoke/0.1"})
    markets, discovery_warnings = discover_polymarket_markets(session)
    started_at = utc_now()
    samples = []
    deadline = time.monotonic() + args.duration_sec
    with open(args.jsonl, "w", encoding="utf-8") as handle:
        while True:
            sample = collect_sample(session, markets)
            if discovery_warnings:
                sample["warnings"].extend(discovery_warnings)
            handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            handle.flush()
            samples.append(sample)
            if time.monotonic() >= deadline:
                break
            time.sleep(args.interval_sec)
    ended_at = utc_now()
    write_summary(args.summary, args.jsonl, samples, started_at, ended_at)
    print(json.dumps({"startedAt": started_at, "endedAt": ended_at, "samples": len(samples), "proxyEnv": proxy_env()}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
