from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pm_lol.config import LIVE_GAME_POLL_INTERVAL_SEC
from pm_lol.models import Game
from pm_lol.sources.lolesports import parse_window
from pm_lol.storage import SQLiteStorage


class LiveStatsClient(Protocol):
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


def _window_state(payload: dict[str, Any], fallback: str) -> str:
    frame = payload.get("sampleFrame") or {}
    return frame.get("gameState") or payload.get("gameState") or fallback
