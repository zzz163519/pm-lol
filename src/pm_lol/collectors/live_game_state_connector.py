from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pm_lol.config import LIVE_GAME_POLL_INTERVAL_SEC
from pm_lol.models import Game, GameStateSnapshot
from pm_lol.sources.lolesports import parse_event_details, parse_window
from pm_lol.storage import SQLiteStorage

# Cito free plan allows <=10 req/min. We stay strictly under that with buffer.
CITO_FREE_PLAN_MAX_REQ_PER_MIN = 10
CITO_DEFAULT_REQUEST_BUDGET_PER_MIN = 6
# 429 backoff must cool down for at least this long before retrying.
CITO_RATE_LIMIT_BACKOFF_SEC = 60

PAUSE_STATES = {"paused", "pause", "remake", "on_break", "onbreak", "on-break"}


class LiveStatsClient(Protocol):
    def get_window(self, game_id: str) -> dict[str, Any]: ...


class CitoVisualStateClient(Protocol):
    def get_visual_state(self, game_id: str) -> dict[str, Any]: ...


class RateLimitedError(Exception):
    """Raised when the Cito visual-state endpoint returns a 429."""


class CitoBudgetScheduler:
    def __init__(
        self,
        request_budget_per_min: int = CITO_DEFAULT_REQUEST_BUDGET_PER_MIN,
        poll_interval_sec: int = LIVE_GAME_POLL_INTERVAL_SEC,
    ) -> None:
        if request_budget_per_min >= CITO_FREE_PLAN_MAX_REQ_PER_MIN:
            raise ValueError(
                "request_budget_per_min must stay under the Cito free-plan limit "
                f"(<{CITO_FREE_PLAN_MAX_REQ_PER_MIN} req/min)"
            )
        if request_budget_per_min <= 0:
            raise ValueError("request_budget_per_min must be positive")
        self.request_budget_per_min = request_budget_per_min
        self.poll_interval_sec = poll_interval_sec
        self.min_interval_sec = max(poll_interval_sec, 60 // request_budget_per_min)

    def plan_offsets(self, targets: list[str], polls_per_target: int) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        offset_sec = 0
        for _ in range(polls_per_target):
            for target in targets:
                plan.append({"offset_sec": offset_sec, "target": target})
                offset_sec += self.min_interval_sec
        return plan


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
        request_budget_per_min: int = CITO_DEFAULT_REQUEST_BUDGET_PER_MIN,
    ) -> dict[str, Any]:
        scheduler = CitoBudgetScheduler(request_budget_per_min, self.poll_interval_sec)
        min_interval_sec = scheduler.min_interval_sec

        polls = 0
        snapshots_written = 0
        fresh_snapshots = 0
        stale_snapshots = 0
        partial_snapshots = 0
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
                backoff_seconds = CITO_RATE_LIMIT_BACKOFF_SEC
                backoff_until = (
                    datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                ).isoformat()
                break

            if snapshot is None:
                skipped_snapshots += 1
            else:
                self.storage.insert_game_state_snapshot(snapshot)
                snapshots_written += 1
                if snapshot.source_status == "fresh":
                    fresh_snapshots += 1
                elif snapshot.source_status == "stale":
                    stale_snapshots += 1
                elif snapshot.source_status == "partial":
                    partial_snapshots += 1

            if self.sleep_func is not None and polls < max_polls:
                self.sleep_func(min_interval_sec)

        return {
            "polls": polls,
            "snapshots_written": snapshots_written,
            "fresh_snapshots": fresh_snapshots,
            "stale_snapshots": stale_snapshots,
            "partial_snapshots": partial_snapshots,
            "skipped_snapshots": skipped_snapshots,
            "rate_limited": rate_limited,
            "request_budget_per_min": request_budget_per_min,
            "min_interval_sec": min_interval_sec,
            "backoff_seconds": backoff_seconds,
            "backoff_until": backoff_until,
        }

    def reconcile_lolesports_game(self, game: Game) -> dict[str, Any]:
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

        winner, winner_error = _per_game_winner(event, game.game_id)
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
        snapshot.source = "lolesports_livestats_window"
        snapshot.winner = winner
        snapshot.error_code = winner_error
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
            "winner_error_code": winner_error,
            "game_state": reconciled_game.state,
        }


def _window_state(payload: dict[str, Any], fallback: str) -> str:
    frame = payload.get("sampleFrame") or {}
    return frame.get("gameState") or payload.get("gameState") or fallback


def _parse_cito_visual_state(payload: dict[str, Any], game: Game) -> GameStateSnapshot | None:
    if payload.get("statusCode") == 429 or payload.get("status") == 429:
        raise RateLimitedError

    body = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    if body.get("status") == "not_ready":
        return None

    last_known = body.get("lastKnownGameplayState") or {}
    blue = body.get("blueTeam") or last_known.get("blueTeam") or {}
    red = body.get("redTeam") or last_known.get("redTeam") or {}
    required_fields = (
        blue.get("gold"),
        red.get("gold"),
        blue.get("kills"),
        red.get("kills"),
        blue.get("towers"),
        red.get("towers"),
    )
    if all(value is None for value in required_fields):
        return None

    status = str(body.get("status") or "partial")
    if status not in {"fresh", "stale"}:
        status = "partial"
    timestamp = _source_timestamp(body)
    rate_limit_state = body.get("rateLimit")
    if not isinstance(rate_limit_state, dict):
        rate_limit_state = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}

    return GameStateSnapshot(
        game_id=game.game_id,
        timestamp=timestamp,
        game_state=str(body.get("gameState") or game.state or "unknown"),
        blue_gold=int(blue.get("gold") or 0),
        red_gold=int(red.get("gold") or 0),
        blue_towers=int(blue.get("towers") or 0),
        red_towers=int(red.get("towers") or 0),
        blue_dragons=_dragon_list(blue.get("dragons")),
        red_dragons=_dragon_list(red.get("dragons")),
        blue_barons=int(blue.get("barons") or 0),
        red_barons=int(red.get("barons") or 0),
        blue_kills=int(blue.get("kills") or 0),
        red_kills=int(red.get("kills") or 0),
        game_clock=_optional_float(body.get("gameTimeSeconds") or body.get("gameTime")),
        source_status=status,
        sample_age_seconds=_optional_int(body.get("sampleAgeSeconds")),
        rate_limit_state=rate_limit_state,
        error_code=None,
        source="cito_visual_state",
        winner=body.get("winner"),
        paused=_parse_paused(body),
        raw=body,
    )


def _parse_paused(body: dict[str, Any]) -> bool | None:
    """Resolve the tri-state pause flag from a source payload.

    Returns True/False only when the source explicitly reports pause status;
    otherwise None (unknown). paused/remake/on-break are never assumed to be
    ``False`` just because we could not observe them.
    """
    for key in ("paused", "isPaused"):
        value = body.get(key)
        if isinstance(value, bool):
            return value
    game_state = str(body.get("gameState") or "").lower()
    if game_state in PAUSE_STATES:
        return True
    return None


def _source_timestamp(body: dict[str, Any]) -> str:
    sampled_at = body.get("sampledAt")
    if isinstance(sampled_at, str) and sampled_at:
        return sampled_at
    if isinstance(sampled_at, dict):
        for value in sampled_at.values():
            if isinstance(value, str) and value:
                return value
    game_id = body.get("gameId") or body.get("requestedGameId") or "unknown"
    age = body.get("sampleAgeSeconds")
    return f"{game_id}:age:{age}"


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


def _per_game_winner(event: dict[str, Any], game_id: str) -> tuple[str | None, str | None]:
    """Resolve the winner of a *single game* from per-game outcomes only.

    Series-level ``gameWins`` is intentionally NOT used as a fallback: a BO3/BO5
    match score cannot identify which team won an individual game. When no
    per-game outcome is available we return ``(None, "winner_unknown")`` rather
    than guessing.
    """
    for game_payload in event.get("match", {}).get("games", []):
        if str(game_payload.get("id")) != str(game_id):
            continue
        for team in game_payload.get("teams", []):
            result = team.get("result") or {}
            if str(result.get("outcome", "")).lower() in {"win", "won"}:
                return str(team.get("id")), None
        # Game is present but no per-game win outcome is recorded.
        return None, "winner_unknown"
    # Target game not present in the payload at all.
    return None, "winner_unknown"
