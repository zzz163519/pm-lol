import sqlite3

from pm_lol.replay_pipeline import run_replay


def test_run_replay_writes_all_phase1_tables(tmp_path):
    db_path = tmp_path / "replay.db"

    summary = run_replay(db_path)

    assert summary["matches"] == 1
    assert summary["games"] >= 1
    assert summary["draft_snapshots"] == 10
    assert summary["game_state_snapshots"] == 1
    assert summary["markets"] == 1
    assert summary["quotes"] >= 1
    assert summary["resolved"] is False

    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "markets",
                "resolved_markets",
                "quotes",
                "matches",
                "games",
                "game_state_snapshots",
                "draft_snapshots",
            )
        }

    assert all(counts[table] > 0 for table in counts)
