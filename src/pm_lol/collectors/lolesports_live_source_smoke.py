from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FetchResult = tuple[dict[str, Any] | None, dict[str, Any]]
Fetcher = Callable[[str, str], FetchResult]

LIVE_STATS_ENDPOINTS = ("window", "details")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect_live_source_smoke(
    game_id: str,
    output_dir: str | Path,
    *,
    fetcher: Fetcher,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    observed_at = now()

    endpoint_reports: dict[str, dict[str, Any]] = {}
    raw_paths: dict[str, str | None] = {}
    payloads: dict[str, dict[str, Any] | None] = {}
    failure_reasons: list[str] = []

    for index, endpoint in enumerate(LIVE_STATS_ENDPOINTS):
        endpoint_observed_at = observed_at if index == 0 else now()
        payload, fetch_record = fetcher(endpoint, game_id)
        payloads[endpoint] = payload
        raw_sample_path = None

        if payload is not None:
            raw_sample_path = output_path / f"lolesports-{game_id}-{endpoint}-raw.json"
            _write_json(raw_sample_path, payload)

        raw_paths[endpoint] = str(raw_sample_path) if raw_sample_path else None
        endpoint_reports[endpoint] = _summarize_endpoint(
            endpoint_observed_at=endpoint_observed_at,
            payload=payload,
            fetch_record=fetch_record,
            raw_sample_path=raw_sample_path,
        )

        if not fetch_record.get("ok"):
            failure_reasons.append(f"{endpoint} failed: {fetch_record.get('errorClass') or fetch_record.get('statusCode')}")

    field_coverage, limitations = _field_coverage(payloads.get("window"), payloads.get("details"))
    for field_name, status in field_coverage.items():
        if field_name == "gameClock":
            continue
        if status == "missing":
            failure_reasons.append(f"required field {field_name} missing")

    if field_coverage["gameClock"] == "missing":
        failure_reasons.append("gameClock cannot be derived because no source frame timestamp was present.")

    report: dict[str, Any] = {
        "source": "lolesports_livestats",
        "gameId": game_id,
        "observedAt": observed_at,
        "overallOk": not failure_reasons,
        "endpoints": endpoint_reports,
        "fieldCoverage": field_coverage,
        "limitations": limitations,
        "failureReasons": failure_reasons,
        "rawSamplePaths": raw_paths,
    }

    report_path = output_path / f"lolesports-{game_id}-live-source-smoke.json"
    raw_paths["report"] = str(report_path)
    _write_json(report_path, report)
    return report


def lolesports_fetcher(timeout_sec: float = 15.0) -> Fetcher:
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": "pm-lol-lolesports-live-source-smoke/0.1"})

    def fetch(endpoint: str, game_id: str) -> FetchResult:
        if endpoint not in LIVE_STATS_ENDPOINTS:
            raise ValueError(f"unsupported endpoint: {endpoint}")

        url = f"https://feed.lolesports.com/livestats/v1/{endpoint}/{game_id}"
        try:
            response = session.get(url, timeout=timeout_sec)
        except requests.RequestException as exc:
            return None, {
                "ok": False,
                "statusCode": None,
                "errorClass": _classify_request_error(str(exc)),
                "error": str(exc),
                "url": url,
            }

        record = {
            "ok": 200 <= response.status_code < 300 and bool(response.content),
            "statusCode": response.status_code,
            "errorClass": None,
            "error": None,
            "url": url,
        }
        if not response.content:
            record["ok"] = False
            record["errorClass"] = "empty_body"
            return None, record
        if response.status_code >= 400:
            record["errorClass"] = "http_error"
            record["error"] = response.text[:500]
            return None, record
        try:
            return response.json(), record
        except ValueError as exc:
            record["ok"] = False
            record["errorClass"] = "parse_error"
            record["error"] = str(exc)
            return None, record

    return fetch


def _summarize_endpoint(
    *,
    endpoint_observed_at: str,
    payload: dict[str, Any] | None,
    fetch_record: dict[str, Any],
    raw_sample_path: Path | None,
) -> dict[str, Any]:
    source_timestamp = _frame_timestamp(payload)
    return {
        "observedAt": endpoint_observed_at,
        "ok": bool(fetch_record.get("ok")),
        "statusCode": fetch_record.get("statusCode"),
        "errorClass": fetch_record.get("errorClass"),
        "error": fetch_record.get("error"),
        "sourceTimestamp": source_timestamp,
        "sourceLatencySec": _latency_sec(endpoint_observed_at, source_timestamp),
        "sourceTimestampNote": None if source_timestamp else "source did not provide a frame timestamp in this response",
        "hasRawSample": raw_sample_path is not None,
        "rawSamplePath": str(raw_sample_path) if raw_sample_path else None,
    }


def _field_coverage(
    window_payload: dict[str, Any] | None,
    details_payload: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str]]:
    frame = _sample_frame(window_payload)
    metadata = (window_payload or {}).get("gameMetadata") or {}
    blue = frame.get("blueTeam") if isinstance(frame, dict) else {}
    red = frame.get("redTeam") if isinstance(frame, dict) else {}
    details_frame = _sample_frame(details_payload)

    coverage = {
        "finalPicks": "present" if _has_final_picks(metadata) else "missing",
        "gameClock": "derived_from_frame_timestamp_only" if _frame_timestamp(window_payload) else "missing",
        "gold": "present" if _has_gold(blue, red) else "missing",
        "objectives": "present" if _has_objectives(blue, red) else "missing",
        "gameState": "present" if isinstance(frame, dict) and frame.get("gameState") else "missing",
    }

    limitations: list[str] = []
    if coverage["gameClock"] == "derived_from_frame_timestamp_only":
        limitations.append("gameClock is not explicit; only derivable from frame timestamps.")
    if details_payload is not None and not isinstance(details_frame, dict):
        limitations.append("details response had no sampleFrame/frames entry.")
    return coverage, limitations


def _sample_frame(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    frame = payload.get("sampleFrame")
    if isinstance(frame, dict):
        return frame
    frames = payload.get("frames")
    if isinstance(frames, list) and frames and isinstance(frames[-1], dict):
        return frames[-1]
    return None


def _frame_timestamp(payload: dict[str, Any] | None) -> str | None:
    frame = _sample_frame(payload)
    if not frame:
        return None
    timestamp = frame.get("rfc460Timestamp")
    return str(timestamp) if timestamp else None


def _has_final_picks(metadata: dict[str, Any]) -> bool:
    teams = [metadata.get("blueTeamMetadata"), metadata.get("redTeamMetadata")]
    champion_count = 0
    for team in teams:
        if not isinstance(team, dict):
            continue
        for participant in team.get("participantMetadata") or []:
            if isinstance(participant, dict) and participant.get("championId"):
                champion_count += 1
    return champion_count >= 10


def _has_gold(blue: Any, red: Any) -> bool:
    return isinstance(blue, dict) and isinstance(red, dict) and blue.get("totalGold") is not None and red.get("totalGold") is not None


def _has_objectives(blue: Any, red: Any) -> bool:
    if not isinstance(blue, dict) or not isinstance(red, dict):
        return False
    objective_keys = ("towers", "dragons", "barons", "inhibitors")
    return all(key in blue and key in red for key in objective_keys)


def _latency_sec(observed_at: str, source_timestamp: str | None) -> float | None:
    observed_dt = _parse_time(observed_at)
    source_dt = _parse_time(source_timestamp)
    if observed_dt is None or source_dt is None:
        return None
    return round(observed_dt.timestamp() - source_dt.timestamp(), 3)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _classify_request_error(message: str) -> str:
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "ssl" in lower or "connection" in lower:
        return "network_error"
    return "request_error"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
