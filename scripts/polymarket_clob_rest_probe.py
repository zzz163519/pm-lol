#!/usr/bin/env python3
"""Record read-only Polymarket CLOB REST samples for one explicit market."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{event_slug}"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []


def select_market(event: dict[str, Any], market_slug: str | None) -> dict[str, Any]:
    markets = event.get("markets") or []
    selected_slug = market_slug or event.get("slug")
    market = next((item for item in markets if item.get("slug") == selected_slug), None)
    if market is None:
        raise ValueError(f"market not found in event: {selected_slug}")
    if not market.get("active") or market.get("closed") or not market.get("acceptingOrders"):
        raise ValueError(f"market is not active and accepting orders: {selected_slug}")
    outcomes = json_list(market.get("outcomes"))
    token_ids = json_list(market.get("clobTokenIds"))
    if len(outcomes) != len(token_ids) or not token_ids:
        raise ValueError(f"invalid outcome/token mapping: {selected_slug}")
    return market


def summarize_book(payload: dict[str, Any]) -> dict[str, Any]:
    def prices(levels: list[dict[str, Any]]) -> list[float]:
        result = []
        for level in levels:
            try:
                result.append(float(level["price"]))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    bids = payload.get("bids") or []
    asks = payload.get("asks") or []
    bid_prices = prices(bids)
    ask_prices = prices(asks)
    return {
        "bestBid": max(bid_prices) if bid_prices else None,
        "bestAsk": min(ask_prices) if ask_prices else None,
        "bidCount": len(bids),
        "askCount": len(asks),
        "sourceTimestamp": payload.get("timestamp"),
    }


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_probe(args: argparse.Namespace) -> int:
    session = requests.Session()
    session.headers["User-Agent"] = "pm-lol-clob-rest-probe/0.1"
    event = session.get(
        GAMMA_EVENT_URL.format(event_slug=args.event_slug), timeout=args.timeout_sec
    ).json()
    market = select_market(event, args.market_slug)
    outcomes = json_list(market.get("outcomes"))
    token_ids = [str(value) for value in json_list(market.get("clobTokenIds"))]
    output = Path(args.output)
    append_record(
        output,
        {
            "type": "probe_start",
            "observedAt": utc_now(),
            "eventSlug": args.event_slug,
            "marketSlug": market.get("slug"),
            "conditionId": market.get("conditionId"),
            "outcomes": outcomes,
            "tokenIds": token_ids,
            "sampleCount": args.sample_count,
            "intervalSec": args.interval_sec,
        },
    )
    errors = 0
    for sample_index in range(args.sample_count):
        for outcome, token_id in zip(outcomes, token_ids):
            started = time.perf_counter()
            observed_at = utc_now()
            try:
                response = session.get(
                    CLOB_BOOK_URL,
                    params={"token_id": token_id},
                    timeout=args.timeout_sec,
                )
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                response.raise_for_status()
                payload = response.json()
                record = {
                    "type": "book",
                    "sampleIndex": sample_index,
                    "observedAt": observed_at,
                    "outcome": outcome,
                    "tokenId": token_id,
                    "httpStatus": response.status_code,
                    "requestLatencyMs": latency_ms,
                    "sourceStatus": "ok",
                    **summarize_book(payload),
                    "raw": payload,
                }
            except (requests.RequestException, ValueError) as exc:
                errors += 1
                record = {
                    "type": "book",
                    "sampleIndex": sample_index,
                    "observedAt": observed_at,
                    "outcome": outcome,
                    "tokenId": token_id,
                    "requestLatencyMs": round((time.perf_counter() - started) * 1000, 3),
                    "sourceStatus": "error",
                    "errorClass": type(exc).__name__,
                    "error": str(exc),
                }
            append_record(output, record)
        if sample_index + 1 < args.sample_count:
            time.sleep(args.interval_sec)
    append_record(output, {"type": "probe_end", "observedAt": utc_now(), "errors": errors})
    return 0 if errors == 0 else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-slug", required=True)
    parser.add_argument("--market-slug")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--interval-sec", type=float, default=30)
    parser.add_argument("--timeout-sec", type=float, default=20)
    args = parser.parse_args()
    if args.sample_count < 1 or args.interval_sec < 0 or args.timeout_sec <= 0:
        parser.error("sample-count must be >=1, interval-sec >=0 and timeout-sec >0")
    return args


if __name__ == "__main__":
    raise SystemExit(run_probe(parse_args()))
