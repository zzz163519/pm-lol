from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pm_lol.config import LIVE_GAME_POLL_INTERVAL_SEC
from pm_lol.models import Game, GameStateSnapshot
from pm_lol.sources.lolesports import parse_event_details, parse_window
from pm_lol.storage import SQLiteStorage

# Cito free plan allows <=10 requests/minute. The connector budgets well under
# that so a handful of poll loops never trip the ceiling, and refuses configs
# that would exceed it.
CITO_FREE_PLAN_MAX_REQ_PER_MIN = 10
RATE_LIMIT_BACKOFF_SECONDS = 60


class RateLimitedError(Exception):
    """Raised when Cito returns HTTP 429 so the poll loop can back off."""


class LiveStatsClient(Protocol):
    def get_window(self, game_id: str) -> dict[str, Any]: ...


class CitoVisualStateClient(Protocol):
    def get_visual_state(self, game_id: str) -> dict[str, Any]: ...


class ReconciliationClient(Protocol):
    def get_event_details(self, match_id: str) -> dict[str, Any]: ...
    def get_window(self, game_id: str) -> dict[str, Any]: ...


class LiveGameStateConnector:
    def __init__(
        self,
        client: LiveStatsClient,
        storage: SQLiteStorage,
        poll_interval_sec: int = LIVE_GAME_POLL_INTERVAL_SEC,
        sleep_func: Callable[[int], None] | None = None,
    ) -> None:
        self.client = client
        self.storage = storage
        self.poll_interval_sec = poll_interval_sec
        self.sleep_func = sleep_func

    def run_game_lifecycle(self, game: Game, max_polls: int = 120) -> dict[str, Any]:
        polls = 0
        state_transitions = [game.state]
        game_state_snapshots = 0
        draft_snapshots = 0
        draft_written = False
        stopped = False

        current_game = game
        while polls < max_polls:
            polls += 1
            payload = self.client.get_window(game.game_id)
            state = _window_state(payload, current_game.state)

            if state != state_transitions[-1]:
                state_transitions.append(state)

            current_game = Game(
                game_id=current_game.game_id,
                match_id=current_game.match_id,
                game_number=current_game.game_number,
                blue_team_id=current_game.blue_team_id,
                red_team_id=current_game.red_team_id,
                state=state,
                patch=payload.get("patchVersion", current_game.patch),
                raw=current_game.raw,
            )
            self.storage.upsert_game(current_game)

            if state == "in_game":
                drafts, snapshot = parse_window(payload)
                self.storage.insert_game_state_snapshot(snapshot)
                game_state_snapshots += 1

                if not draft_written:
                    blue_champions = [draft.champion_id for draft in drafts if draft.side == "blue"]
                    red_champions = [draft.champion_id for draft in drafts if draft.side == "red"]
                    for draft in drafts:
                        self.storage.insert_draft_snapshot(
                            draft,
                            blue_team_id=current_game.blue_team_id,
                            red_team_id=current_game.red_team_id,
                            blue_champions=blue_champions,
                            red_champions=red_champions,
                        )
                    draft_snapshots += len(drafts)
                    draft_written = True

            if state in {"finished", "completed"}:
                stopped = True
                break

            if self.sleep_func is not None:
                self.sleep_func(self.poll_interval_sec)

        return {
            "polls": polls,
            "state_transitions": state_transitions,
            "game_state_snapshots": game_state_snapshots,
            "draft_snapshots": draft_snapshots,
            "stopped": stopped,
        }

    def run_cito_visual_poll(
        self,
        game: Game,
        max_polls: int = 4,
        request_budget_per_min: int = 3,
    ) -> dict[str, Any]:
        """Low-frequency Cito visual-state polling.

        Every stored snapshot is tagged fresh/stale/partial with its sample age.
        A not-ready or empty payload is skipped (no fabricated snapshot). HTTP 429
        stops the loop and reports a >=60s backoff without writing anything.
        """
        if request_budget_per_min < 1:
            raise ValueError("request_budget_per_min must be at least 1")
        if request_budget_per_min > CITO_FREE_PLAN_MAX_REQ_PER_MIN:
            raise ValueError(
                "request_budget_per_min must stay within the Cito free-plan "
                f"ceiling of {CITO_FREE_PLAN_MAX_REQ_PER_MIN} req/min"
            )

        interval_sec = max(self.poll_interval_sec, 60 // request_budget_per_min)
        counters = {"fresh": 0, "stale": 0, "partial": 0}
        polls = 0
        snapshots_written = 0
        skipped_snapshots = 0
        rate_limited = False
        backoff_seconds: int | None = None
        backoff_until: str | None = None

        for _ in range(max_polls):
            polls += 1
            try:
                payload = self.client.get_visual_state(game.game_id)  # type: ignore[attr-defined]
                snapshot = _parse_cito_visual_state(payload, game)
            except RateLimitedError:
                rate_limited = True
                backoff_seconds = RATE_LIMIT_BACKOFF_SECONDS
                backoff_until = (
                    datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                ).isoformat()
                break

            if snapshot is None:
                skipped_snapshots += 1
            else:
                self.storage.insert_game_state_snapshot(snapshot)
                snapshots_written += 1
                counters[snapshot.source_status] = counters.get(snapshot.source_status, 0) + 1

            if self.sleep_func is not None and polls < max_polls:
                self.sleep_func(interval_sec)

        return {
            "polls": polls,
            "snapshots_written": snapshots_written,
            "fresh_snapshots": counters["fresh"],
            "stale_snapshots": counters["stale"],
            "partial_snapshots": counters["partial"],
            "skipped_snapshots": skipped_snapshots,
            "rate_limited": rate_limited,
            "request_budget_per_min": request_budget_per_min,
            "poll_interval_sec": interval_sec,
            "backoff_seconds": backoff_seconds,
            "backoff_until": backoff_until,
        }

    def reconcile_lolesports_game(self, game: Game) -> dict[str, Any]:
        """Reconcile a finished game against LoLEsports event details.

        Writes final picks and the per-game winner. The winner is read strictly
        from the game-level team outcome; the match-level series score is never
        used to infer a single game's winner. When no per-game outcome exists the
        winner stays NULL and the snapshot carries ``error_code='winner_unknown'``.
        """
        event_payload = self.client.get_event_details(game.match_id)  # type: ignore[attr-defined]
        event = event_payload.get("event") or event_payload.get("data", {}).get("event")
        if event is None:
            raise ValueError("event details payload has no event")

        _, games = parse_event_details({"event": event})
        reconciled_game = next(
            (candidate for candidate in games if candidate.game_id == game.game_id), None
        )
        if reconciled_game is None:
            raise ValueError(f"event details payload has no game {game.game_id}")

        winner = _winner_team_id(event, game.game_id)
        current_game = Game(
            game_id=game.game_id,
            match_id=game.match_id,
            game_number=game.game_number,
            blue_team_id=game.blue_team_id,
            red_team_id=game.red_team_id,
            state=reconciled_game.state,
            patch=game.patch,
            raw=reconciled_game.raw,
        )
        self.storage.upsert_game(current_game)

        window_payload = self.client.get_window(game.game_id)
        drafts, snapshot = parse_window(window_payload)
        snapshot.source_status = "final"
        snapshot.source = "lolesports_event_details_reconciliation"
        snapshot.winner = winner
        if winner is None:
            snapshot.error_code = "winner_unknown"
        self.storage.insert_game_state_snapshot(snapshot)

        blue_champions = [draft.champion_id for draft in drafts if draft.side == "blue"]
        red_champions = [draft.champion_id for draft in drafts if draft.side == "red"]
        for draft in drafts:
            self.storage.insert_draft_snapshot(
                draft,
                blue_team_id=current_game.blue_team_id,
                red_team_id=current_game.red_team_id,
                blue_champions=blue_champions,
                red_champions=red_champions,
            )

        return {
            "match_id": game.match_id,
            "game_id": game.game_id,
            "draft_snapshots": len(drafts),
            "winner": winner,
            "winner_known": winner is not None,
            "error_code": snapshot.error_code,
            "game_state": reconciled_game.state,
        }


def _window_state(payload: dict[str, Any], fallback: str) -> str:
    frame = payload.get("sampleFrame") or {}
    return frame.get("gameState") or payload.get("gameState") or fallback


def _parse_cito_visual_state(payload: dict[str, Any], game: Game) -> GameStateSnapshot | None:
    """Turn a Cito visual-state payload into a snapshot, or None to skip.

    Returns None for not-ready / empty numeric state so no fabricated snapshot is
    written. Raises RateLimitedError on HTTP 429.
    """
    if payload.get("statusCode") == 429 or payload.get("status") == 429:
        raise RateLimitedError

    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    if str(body.get("status") or "").lower() == "not_ready":
        return None

    last_known = body.get("lastKnownGameplayState") or {}
    blue = body.get("blueTeam") or last_known.get("blueTeam") or {}
    red = body.get("redTeam") or last_known.get("redTeam") or {}

    numeric_fields = (
        blue.get("gold"),
        red.get("gold"),
        blue.get("kills"),
        red.get("kills"),
        blue.get("towers"),
        red.get("towers"),
    )
    if all(value is None for value in numeric_fields):
        # No usable numeric state — treat as not ready rather than fabricate zeros.
        return None

    freshness = _classify_freshness(body)
    partial = any(value is None for value in numeric_fields)
    source_status = "partial" if partial else freshness
    error_code = "partial_fields" if partial else None

    rate_limit_state = body.get("rateLimit")
    if not isinstance(rate_limit_state, dict):
        headers = payload.get("headers")
        rate_limit_state = headers if isinstance(headers, dict) else {}

    game_time = body.get("gameTimeSeconds")
    if game_time is None:
        game_time = body.get("gameTime")

    # paused is not reported reliably by Cito visual state; keep it unknown (None)
    # unless the payload states it explicitly, never a hardcoded False.
    paused = body.get("paused")
    if not isinstance(paused, bool):
        paused = None

    return GameStateSnapshot(
        game_id=game.game_id,
        timestamp=_source_timestamp(body, game),
        game_state=str(body.get("gameState") or game.state or "unknown"),
        blue_gold=_optional_int(blue.get("gold")) or 0,
        red_gold=_optional_int(red.get("gold")) or 0,
        blue_towers=_optional_int(blue.get("towers")) or 0,
        red_towers=_optional_int(red.get("towers")) or 0,
        blue_dragons=_dragon_list(blue.get("dragons")),
        red_dragons=_dragon_list(red.get("dragons")),
        blue_barons=_optional_int(blue.get("barons")) or 0,
        red_barons=_optional_int(red.get("barons")) or 0,
        blue_kills=_optional_int(blue.get("kills")) or 0,
        red_kills=_optional_int(red.get("kills")) or 0,
        game_clock=_optional_float(game_time),
        paused=paused,
        source_status=source_status,
        sample_age_seconds=_sample_age(body),
        rate_limit_state=rate_limit_state,
        error_code=error_code,
        source="cito_visual_state",
        winner=None,
        raw=body,
    )


def _classify_freshness(body: dict[str, Any]) -> str:
    status = body.get("status")
    if isinstance(status, str) and status.lower() in {"fresh", "stale"}:
        return status.lower()

    freshness = body.get("freshness")
    if isinstance(freshness, dict) and "isFresh" in freshness:
        return "fresh" if freshness["isFresh"] else "stale"

    age = _sample_age(body)
    threshold = freshness.get("staleAfterSeconds") if isinstance(freshness, dict) else None
    if age is not None and threshold is not None:
        return "fresh" if age <= threshold else "stale"
    return "partial"


def _sample_age(body: dict[str, Any]) -> int | None:
    for key in ("sampleAgeSeconds", "lastKnownGameplayAgeSeconds"):
        value = body.get(key)
        if value is not None:
            return int(value)
    return None


def _source_timestamp(body: dict[str, Any], game: Game) -> str:
    sampled_at = body.get("sampledAt") or body.get("lastCheckedAt")
    if isinstance(sampled_at, str) and sampled_at:
        return sampled_at
    game_time = body.get("gameTimeSeconds")
    age = _sample_age(body)
    return f"{game.game_id}:gt{game_time}:age{age}"


def _dragon_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, int):
        return ["unknown"] * value
    return []


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _winner_team_id(event: dict[str, Any], game_id: str) -> str | None:
    """Per-game winner from the game-level team outcome only.

    Deliberately does NOT fall back to the match-level series score (gameWins):
    in a BO-N series a game can be won by the team that loses the series, so the
    series score cannot identify a single game's winner. Unknown -> None.
    """
    for game_payload in event.get("match", {}).get("games", []):
        if str(game_payload.get("id")) != str(game_id):
            continue
        for team in game_payload.get("teams", []):
            result = team.get("result") or {}
            if str(result.get("outcome", "")).lower() in {"win", "won"}:
                return str(team.get("id"))
        # Matched the game but no team is marked as the winner: unknown.
        return None
    return None
