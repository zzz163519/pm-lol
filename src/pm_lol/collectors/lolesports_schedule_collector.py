from __future__ import annotations

from typing import Any, Protocol

from pm_lol.sources.lolesports import parse_event_details
from pm_lol.storage import SQLiteStorage


class ScheduleClient(Protocol):
    def get_leagues(self) -> dict[str, Any]: ...
    def get_schedule(self) -> dict[str, Any]: ...
    def get_event_details(self, match_id: str) -> dict[str, Any]: ...


class ScheduleCollector:
    def __init__(self, client: ScheduleClient, storage: SQLiteStorage) -> None:
        self.client = client
        self.storage = storage

    def run_once(self) -> dict[str, int]:
        leagues_payload = self.client.get_leagues()
        schedule_payload = self.client.get_schedule()
        events = _extract_events(schedule_payload)

        matches_written = 0
        games_written = 0
        for event in events:
            match_id = _event_match_id(event)
            if not match_id:
                continue
            match, games = parse_event_details(self.client.get_event_details(match_id))
            self.storage.upsert_match(match)
            matches_written += 1
            for game in games:
                self.storage.upsert_game(game)
                games_written += 1

        return {
            "leagues_seen": len(_extract_leagues(leagues_payload)),
            "events_seen": len(events),
            "matches_written": matches_written,
            "games_written": games_written,
        }


def _extract_leagues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", payload)
    return data.get("leagues", [])


def _extract_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", payload)
    schedule = data.get("schedule", data)
    return schedule.get("events", data.get("events", []))


def _event_match_id(event: dict[str, Any]) -> str | None:
    if event.get("match_id"):
        return str(event["match_id"])
    if event.get("id") and event.get("type") == "match":
        return str(event["id"])
    match = event.get("match") or {}
    if match.get("id"):
        return str(match["id"])
    return None
