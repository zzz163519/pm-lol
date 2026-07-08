#!/usr/bin/env python3
"""Offline, read-only smoke for LiveGameStateConnector v1 (CAL-69).

Drives the connector end-to-end against checked-in fixtures — no network calls,
no API keys, no wallet/order/strategy paths — and writes a sample artifact that
demonstrates the two hardened contracts:

* ``paused`` unknown is persisted as NULL (never a fabricated ``False``).
* single-game winner is only taken from per-game outcomes; a BO5 series score is
  never used to infer it (missing outcome -> ``winner_unknown``).

Usage::

    .venv/bin/python scripts/live_game_state_connector_smoke.py \
        --out docs/source-spike/cal-69-live-game-state-connector-smoke.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pm_lol.collectors.live_game_state_connector import LiveGameStateConnector
from pm_lol.models import Game, Match
from pm_lol.storage import SQLiteStorage

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOW_FIXTURE = REPO_ROOT / "docs" / "source-spike" / "lolesports-window-t1-gen-g1-15m-sample.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "source-spike" / "cal-69-live-game-state-connector-smoke.json"


class CannedCitoClient:
    """Returns pre-baked Cito visual-state payloads (fresh / stale / paused-unknown)."""

    def __init__(self, payloads):
        self._payloads = list(payloads)

    def get_visual_state(self, game_id):
        return self._payloads.pop(0)


class CannedLolEsportsClient:
    """Returns a pre-baked getEventDetails payload plus the fixture window."""

    def __init__(self, event, game_state):
        self._event = event
        self._game_state = game_state

    def get_event_details(self, match_id):
        return {"event": self._event}

    def get_window(self, game_id):
        payload = json.loads(WINDOW_FIXTURE.read_text())
        payload["esportsGameId"] = game_id
        payload["esportsMatchId"] = self._event["id"]
        payload["sampleFrame"]["gameState"] = self._game_state
        return payload


def _cito_payload(game_id, *, status, sampled_at, sample_age, game_state=None):
    payload = {
        "success": True,
        "source": "visual_live_extraction",
        "status": status,
        "sampleAgeSeconds": sample_age,
        "sampledAt": sampled_at,
        "gameId": game_id,
        "gameTimeSeconds": 1146,
        "blueTeam": {"tag": "BLU", "gold": 34700, "kills": 10, "towers": 0, "dragons": 1},
        "redTeam": {"tag": "RED", "gold": 36800, "kills": 13, "towers": 3, "dragons": 3},
        "rateLimit": {"remaining": 150},
    }
    if game_state is not None:
        payload["gameState"] = game_state
    return payload


def run_smoke(out_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        storage = SQLiteStorage(Path(tmp) / "smoke.db")

        # --- Cito low-frequency visual poll: fresh, stale, and paused-unknown ---
        cito_match = Match(
            match_id="smoke-cito-match",
            league="SMOKE",
            team_a_id="blue-team",
            team_a_name="Blue Team",
            team_b_id="red-team",
            team_b_name="Red Team",
        )
        cito_game = Game(
            game_id="smoke-cito-game",
            match_id=cito_match.match_id,
            game_number=1,
            blue_team_id=cito_match.team_a_id,
            red_team_id=cito_match.team_b_id,
            state="in_game",
        )
        storage.upsert_match(cito_match)
        storage.upsert_game(cito_game)

        cito_client = CannedCitoClient(
            [
                _cito_payload(cito_game.game_id, status="fresh", sampled_at="2026-07-08T09:14:18Z", sample_age=18),
                _cito_payload(cito_game.game_id, status="stale", sampled_at="2026-07-08T09:14:52Z", sample_age=142),
            ]
        )
        cito_summary = LiveGameStateConnector(cito_client, storage).run_cito_visual_poll(
            cito_game, max_polls=2
        )
        cito_snapshots = storage.get_game_state_snapshots(cito_game.game_id)

        # --- LoLEsports reconciliation: BO5 game with NO per-game outcome ---
        bo5_match = Match(
            match_id="smoke-bo5-match",
            league="SMOKE",
            team_a_id="series-winner",
            team_a_name="Series Winner",
            team_b_id="series-loser",
            team_b_name="Series Loser",
        )
        bo5_game = Game(
            game_id="smoke-bo5-g2",
            match_id=bo5_match.match_id,
            game_number=2,
            blue_team_id=bo5_match.team_a_id,
            red_team_id=bo5_match.team_b_id,
            state="in_game",
        )
        storage.upsert_match(bo5_match)
        storage.upsert_game(bo5_game)

        bo5_event = {
            "id": "smoke-bo5-match",
            "state": "completed",
            "match": {
                "teams": [
                    {"id": "series-winner", "name": "Series Winner", "result": {"gameWins": 3}},
                    {"id": "series-loser", "name": "Series Loser", "result": {"gameWins": 2}},
                ],
                "games": [
                    {
                        "id": "smoke-bo5-g2",
                        "number": 2,
                        "state": "completed",
                        "teams": [
                            {"id": "series-winner", "side": "blue"},
                            {"id": "series-loser", "side": "red"},
                        ],
                    }
                ],
            },
        }
        bo5_summary = LiveGameStateConnector(
            CannedLolEsportsClient(bo5_event, "completed"), storage
        ).reconcile_lolesports_game(bo5_game)
        bo5_snapshots = storage.get_game_state_snapshots(bo5_game.game_id)

    artifact = {
        "artifact": "cal-69-live-game-state-connector-smoke",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "offline_read_only_fixture",
        "boundaries": "read-only; no strategy/signal/order/wallet/private-key; no API key printed",
        "cito_visual_poll": {
            "summary": cito_summary,
            "snapshots": [
                {
                    "source_status": s.source_status,
                    "sample_age_seconds": s.sample_age_seconds,
                    "game_clock": s.game_clock,
                    "paused": s.paused,  # None => unknown, never fabricated False
                    "source": s.source,
                }
                for s in cito_snapshots
            ],
        },
        "bo5_reconciliation": {
            "summary": bo5_summary,
            "snapshot": {
                "winner": bo5_snapshots[0].winner,  # None => unknown
                "error_code": bo5_snapshots[0].error_code,  # winner_unknown
                "source_status": bo5_snapshots[0].source_status,
                "paused": bo5_snapshots[0].paused,
            },
            "note": "series was 3-2 but the individual game winner is NOT inferred from gameWins",
        },
    }

    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    artifact = run_smoke(args.out)
    print(f"wrote {args.out}")
    print(json.dumps(artifact["cito_visual_poll"]["snapshots"], indent=2))
    print(json.dumps(artifact["bo5_reconciliation"]["snapshot"], indent=2))


if __name__ == "__main__":
    main()
