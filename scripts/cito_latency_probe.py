#!/usr/bin/env python3
"""Read-only Cito visual-state latency probe for CAL-55."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import requests


CITO_BASE_URL = "https://api.citoapi.com/api/v1"
CLOB_BOOK_URL = "https://clob.polymarket.com/book?token_id={token_id}"
DEFAULT_GAME_ID = "115570934355614589"
DEFAULT_MATCH_ID = "115570934355614587"
DEFAULT_MARKET_SLUG = "lol-ly-tsw-2026-07-08-game2"
DEFAULT_TOKENS = (
    ("LYON", "100457005292152153372253202061468738617711922867164825681469038114409110255689"),
    ("Team Secret Whales", "25106904841758773473490359607223285312752109742817439651788740246841101764476"),
)


HttpGet = Callable[[str], tuple[Any | None, dict[str, Any]]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_cito_api_key(env_path: Path = Path(".env")) -> str | None:
    value = os.environ.get("CITO_API_KEY")
    if value:
        return value
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() == "CITO_API_KEY":
            value = raw_value.strip().strip('"').strip("'")
            if value:
                os.environ["CITO_API_KEY"] = value
                return value
    return None


def real_http_get(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[Any | None, dict[str, Any]]:
    started = time.monotonic()
    observed_at = utc_now()
    try:
        response = session.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return None, {
            "observedAt": observed_at,
            "elapsedSec": round(time.monotonic() - started, 3),
            "url": url,
            "ok": False,
            "statusCode": None,
            "error": str(exc),
        }

    record = {
        "observedAt": observed_at,
        "elapsedSec": round(time.monotonic() - started, 3),
        "url": url,
        "ok": 200 <= response.status_code < 300,
        "statusCode": response.status_code,
        "error": None,
    }
    if not response.content:
        return None, record
    try:
        return response.json(), record
    except ValueError as exc:
        record["ok"] = False
        record["error"] = str(exc)
        return None, record


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


def team_summary(team: Any) -> dict[str, Any]:
    if not isinstance(team, dict):
        return {"tag": None, "kills": None, "gold": None, "towers": None, "dragons": None, "barons": None}
    return {
        "tag": first_text(team.get("tag"), team.get("code"), team.get("name")),
        "kills": first_number(team.get("kills")),
        "gold": first_number(team.get("gold")),
        "towers": first_number(team.get("towers")),
        "dragons": first_number(team.get("dragons")),
        "barons": first_number(team.get("barons")),
    }


def nested_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def summarize_visual_state(payload: Any, observed_at: str) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    data = nested_data(body)
    game_time_seconds = first_number(
        body.get("gameTimeSeconds"),
        body.get("gameTime"),
        data.get("gameTimeSeconds"),
        data.get("gameTime"),
    )
    sample_age_seconds = first_number(
        body.get("sampleAgeSeconds"),
        body.get("lastKnownGameplayAgeSeconds"),
        data.get("sampleAgeSeconds"),
    )
    source_latency_basis = (
        "cito_sampleAgeSeconds_proxy"
        if sample_age_seconds is not None
        else "not_computable_no_cito_source_timestamp_or_sample_age"
    )
    freshness = body.get("freshness") if isinstance(body.get("freshness"), dict) else {}
    return {
        "observedAt": observed_at,
        "status": body.get("status"),
        "message": body.get("message"),
        "gameClock": first_text(body.get("gameTimeFormatted"), data.get("gameTimeFormatted")),
        "gameTimeSeconds": game_time_seconds,
        "sampleAgeSeconds": sample_age_seconds,
        "sourceLatencySec": sample_age_seconds,
        "sourceLatencyBasis": source_latency_basis,
        "isFresh": freshness.get("isFresh") if freshness else None,
        "staleAfterSeconds": freshness.get("staleAfterSeconds") if freshness else None,
        "blue": team_summary(body.get("blueTeam") or data.get("blueTeam")),
        "red": team_summary(body.get("redTeam") or data.get("redTeam")),
        "confidence": body.get("confidence") if isinstance(body.get("confidence"), dict) else None,
        "validation": body.get("validation") if isinstance(body.get("validation"), dict) else None,
        "quality": body.get("dataQuality") if isinstance(body.get("dataQuality"), dict) else None,
        "rawHasSampledAt": body.get("sampledAt") not in (None, {}, []),
    }


def clob_timestamp_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    # Polymarket CLOB timestamp is milliseconds, but may be monotonic/skewed.
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)


def sorted_price_levels(levels: Any, *, reverse: bool) -> list[dict[str, Any]]:
    if not isinstance(levels, list):
        return []
    parsed = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        try:
            price = float(level.get("price"))
            size = float(level.get("size"))
        except (TypeError, ValueError):
            continue
        parsed.append({"price": price, "size": size})
    return sorted(parsed, key=lambda item: item["price"], reverse=reverse)


def summarize_polymarket_book(payload: Any, observed_at: str, outcome: str, token_id: str) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    bids = sorted_price_levels(body.get("bids"), reverse=True)
    asks = sorted_price_levels(body.get("asks"), reverse=False)
    observed_dt = parse_time(observed_at)
    source_dt = clob_timestamp_to_datetime(body.get("timestamp"))
    source_latency_sec = None
    if observed_dt and source_dt:
        source_latency_sec = round(observed_dt.timestamp() - source_dt.timestamp(), 3)
    return {
        "observedAt": observed_at,
        "outcome": outcome,
        "tokenId": token_id,
        "sourceTimestamp": str(body.get("timestamp")) if body.get("timestamp") is not None else None,
        "sourceLatencySec": source_latency_sec,
        "bestBid": bids[0]["price"] if bids else None,
        "bestAsk": asks[0]["price"] if asks else None,
        "bidCount": len(bids),
        "askCount": len(asks),
    }


def numeric_summary(values: list[int | float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "mean": round(statistics.mean(values), 3),
        "max": round(max(values), 3),
    }


def unique_confidences(iterations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    values = []
    for item in iterations:
        confidence = ((item.get("metrics") or {}).get("citoVisualState") or {}).get("confidence")
        if not isinstance(confidence, dict):
            continue
        key = json.dumps(confidence, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        values.append(confidence)
    return values


def compute_latency_report(iterations: list[dict[str, Any]]) -> dict[str, Any]:
    cito_latencies = []
    game_times = []
    polymarket_latencies = []
    for item in iterations:
        metrics = item.get("metrics") or {}
        cito = metrics.get("citoVisualState") or {}
        if isinstance(cito.get("sourceLatencySec"), (int, float)):
            cito_latencies.append(cito["sourceLatencySec"])
        if isinstance(cito.get("gameTimeSeconds"), (int, float)):
            game_times.append(cito["gameTimeSeconds"])
        for book in metrics.get("polymarketBooks") or []:
            if isinstance(book.get("sourceLatencySec"), (int, float)):
                polymarket_latencies.append(book["sourceLatencySec"])

    confidence_values = unique_confidences(iterations)
    tracked_fields = ("gold", "kills", "objectives", "timer")
    tracked_values = {
        field: [value.get(field) for value in confidence_values if isinstance(value, dict) and field in value]
        for field in tracked_fields
    }
    tracked_fields_always_one = bool(confidence_values) and all(
        values and set(values) == {1} for values in tracked_values.values()
    )
    confidence_conclusion = "not_observed"
    if tracked_fields_always_one:
        confidence_conclusion = "tracked_fields_always_one_treat_as_unverified_not_calibrated"
    elif confidence_values:
        confidence_conclusion = "variable_values_observed_but_calibration_unverified"

    advanced = sum(
        1 for previous, current in zip(game_times, game_times[1:]) if current is not None and previous is not None and current > previous
    )
    return {
        "cito": {
            "samples": len(iterations),
            "sourceLatencySecProxy": numeric_summary(cito_latencies),
            "gameTimeAdvancedSamples": advanced,
            "latencyConclusion": (
                "proxy_only_sampleAgeSeconds_not_true_observedAt_minus_source_timestamp"
                if cito_latencies
                else "not_computable_no_source_timestamp_or_sample_age"
            ),
            "confidenceAssessment": {
                "observedUniqueValues": confidence_values,
                "trackedFields": list(tracked_fields),
                "trackedFieldValues": tracked_values,
                "trackedFieldsAlwaysOne": tracked_fields_always_one,
                "conclusion": confidence_conclusion,
            },
        },
        "polymarket": {
            "sourceLatencySec": numeric_summary(polymarket_latencies),
            "timestampNote": "CLOB timestamp latency uses local observedAt minus orderbook timestamp; small negative values indicate clock/skew risk.",
        },
    }


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_markdown_report(path: Path, result: dict[str, Any]) -> str:
    report = result["latencyReport"]
    cito = report["cito"]["sourceLatencySecProxy"]
    poly = report["polymarket"]["sourceLatencySec"]
    confidence = report["cito"]["confidenceAssessment"]
    lines = [
        "# CAL-55 Cito Source Latency Probe",
        "",
        f"Window: `{result['startedAt']}` to `{result['endedAt']}` UTC.",
        "",
        "Read-only scope: no wallet, no private key, no order placement, no strategy, no prediction, no trading signal.",
        "",
        "## Inputs",
        "",
        f"- Cito endpoint: `/api/v1/lol/live/{result['gameId']}/visual-state`",
        f"- Polymarket market: `{result['polymarket']['marketSlug']}`",
        f"- Samples: `{len(result['iterations'])}` at requested interval `{result['pollIntervalSec']}s`",
        "",
        "## Latency",
        "",
        f"- Cito sourceLatencySec: `{report['cito']['latencyConclusion']}`.",
        f"- Cito proxy range from `sampleAgeSeconds`: min `{cito['min']}`, median `{cito['median']}`, mean `{cito['mean']}`, max `{cito['max']}` seconds.",
        f"- Polymarket CLOB timestamp latency: min `{poly['min']}`, median `{poly['median']}`, mean `{poly['mean']}`, max `{poly['max']}` seconds.",
        "",
        "Cito did not expose a usable server source timestamp in this response shape; `sampleAgeSeconds` is therefore a freshness proxy, not true `observedAt - sourceTimestamp` latency.",
        "",
        "## Confidence",
        "",
        f"- Observed unique confidence maps: `{json.dumps(confidence['observedUniqueValues'], ensure_ascii=False, sort_keys=True)}`",
        f"- Tracked requested fields (`gold/kills/objectives/timer`) all stayed at `1`: `{confidence['trackedFieldsAlwaysOne']}`",
        f"- Conclusion: `{confidence['conclusion']}`.",
        "",
        "## Verdict",
        "",
        result["verdict"],
        "",
        "Raw JSON: `" + result["rawSamplePath"] + "`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def build_verdict(latency_report: dict[str, Any]) -> str:
    cito = latency_report["cito"]["sourceLatencySecProxy"]
    if cito["count"] == 0:
        return (
            "Cito visual-state cannot be evaluated as a Phase 1 source from this run because no sampleAgeSeconds/source timestamp "
            "was exposed. Keep it behind a hard freshness gate and do not promote it."
        )
    return (
        "Cito visual-state is acceptable only as a candidate backup/live input behind a freshness gate in the observed proxy range, "
        f"not as a confirmed primary source: this run measured `sampleAgeSeconds` {cito['min']}-{cito['max']}s "
        "and still lacks a true source timestamp. Treat confidence=1 fields as uncalibrated until Cito documents their semantics "
        "or a postgame reconciliation proves accuracy."
    )


def run_probe(
    *,
    cito_api_key: str,
    game_id: str,
    match_id: str,
    market_slug: str,
    token_pairs: list[tuple[str, str]],
    output_dir: Path,
    duration_sec: int,
    poll_interval_sec: int,
    http_get: HttpGet,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    started_at = now()
    iterations = []
    deadline = time.monotonic() + duration_sec
    iteration = 0
    while True:
        iteration += 1
        cito_payload, cito_record = http_get(
            f"{CITO_BASE_URL}/lol/live/{game_id}/visual-state",
            headers={"x-api-key": cito_api_key},
        )
        cito_summary = summarize_visual_state(cito_payload, cito_record.get("observedAt") or now())
        book_records = []
        book_summaries = []
        for outcome, token_id in token_pairs:
            book_payload, book_record = http_get(CLOB_BOOK_URL.format(token_id=token_id))
            book_records.append({"outcome": outcome, "tokenId": token_id, "request": book_record, "body": book_payload})
            book_summaries.append(
                summarize_polymarket_book(book_payload, book_record.get("observedAt") or now(), outcome, token_id)
            )

        iterations.append(
            {
                "iteration": iteration,
                "observedAt": now(),
                "records": {
                    "citoVisualState": {"request": cito_record, "body": cito_payload},
                    "polymarketBooks": book_records,
                },
                "metrics": {
                    "citoVisualState": cito_summary,
                    "polymarketBooks": book_summaries,
                },
            }
        )
        if time.monotonic() >= deadline:
            break
        sleep(poll_interval_sec)

    ended_at = now()
    result = {
        "script": "scripts/cito_latency_probe.py",
        "scope": "CAL-55 Cito visual-state sourceLatencySec probe",
        "startedAt": started_at,
        "endedAt": ended_at,
        "gameId": game_id,
        "matchId": match_id,
        "pollIntervalSec": poll_interval_sec,
        "durationSecRequested": duration_sec,
        "polymarket": {
            "marketSlug": market_slug,
            "tokens": [{"outcome": outcome, "tokenId": token_id} for outcome, token_id in token_pairs],
        },
        "iterations": iterations,
        "latencyReport": compute_latency_report(iterations),
        "boundaryFindings": [
            "read_only_get_requests_only",
            "no_wallet",
            "no_private_key",
            "no_trade_execution",
            "no_strategy_or_signal",
        ],
    }
    result["verdict"] = build_verdict(result["latencyReport"])
    raw_path = output_dir / "cito-source-latency-cal55-20260708.json"
    result["rawSamplePath"] = str(raw_path)
    write_json(raw_path, result)
    report_path = output_dir / "cito-source-latency-cal55-20260708.md"
    result["reportPath"] = write_markdown_report(report_path, result)
    write_json(raw_path, result)
    return result


def parse_token(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("token must be OUTCOME=TOKEN_ID")
    outcome, token_id = value.split("=", 1)
    if not outcome or not token_id:
        raise argparse.ArgumentTypeError("token must be OUTCOME=TOKEN_ID")
    return outcome, token_id


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default=DEFAULT_GAME_ID)
    parser.add_argument("--match-id", default=DEFAULT_MATCH_ID)
    parser.add_argument("--market-slug", default=DEFAULT_MARKET_SLUG)
    parser.add_argument("--token", action="append", type=parse_token, dest="tokens")
    parser.add_argument("--duration-sec", type=int, default=310)
    parser.add_argument("--poll-interval-sec", type=int, default=10)
    parser.add_argument("--output-dir", default="docs/source-spike")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    api_key = load_cito_api_key(Path(".env"))
    if not api_key:
        print("CITO_API_KEY is missing; no Cito request sent.", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-cito-latency-probe/0.1"})

    def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 15.0):
        return real_http_get(session, url, headers=headers, timeout=timeout)

    result = run_probe(
        cito_api_key=api_key,
        game_id=args.game_id,
        match_id=args.match_id,
        market_slug=args.market_slug,
        token_pairs=args.tokens or list(DEFAULT_TOKENS),
        output_dir=Path(args.output_dir),
        duration_sec=args.duration_sec,
        poll_interval_sec=args.poll_interval_sec,
        http_get=http_get,
    )
    print(json.dumps(result["latencyReport"], ensure_ascii=False, indent=2, sort_keys=True))
    print(result["reportPath"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
