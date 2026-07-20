from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pm_lol.collectors.live_game_state_connector import LiveGameStateConnector
from pm_lol.sources.lolesports import LoLEsportsClient, parse_event_details
from pm_lol.storage import SQLiteStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "live.db"
LOLESPORTS_API_KEY_ENV = "LOLESPORTS_API_KEY"


def load_lolesports_api_key() -> str:
    api_key = os.environ.get(LOLESPORTS_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{LOLESPORTS_API_KEY_ENV} is required")
    return api_key


def run_live_runner(match_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    client = LoLEsportsClient(api_key=load_lolesports_api_key())
    payload = client.get_event_details(match_id)
    event = payload["data"]["event"]
    match, games = parse_event_details({"event": event})

    storage = SQLiteStorage(db_path)
    storage.upsert_match(match)
    for game in games:
        storage.upsert_game(game)

    active_game = next((game for game in games if game.state == "inProgress"), None)
    if active_game is None:
        active_game = next((game for game in games if game.state != "completed"), games[-1])

    connector = LiveGameStateConnector(client, storage, sleep_func=time.sleep)
    lifecycle = connector.run_game_lifecycle(active_game)

    return {
        "match_id": match.match_id,
        "league": match.league,
        "games": len(games),
        "active_game_id": active_game.game_id,
        "db_path": str(Path(db_path)),
        "lifecycle": lifecycle,
    }


def main() -> None:
    match_id = sys.argv[1] if len(sys.argv) > 1 else "116634566264113564"
    result = run_live_runner(match_id)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
