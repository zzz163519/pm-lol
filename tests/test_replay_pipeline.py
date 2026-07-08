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
        quote_rows = conn.execute(
            """
            SELECT market_slug, game_number, outcome, source_status
            FROM quotes
            ORDER BY token_id
            """
        ).fetchall()

    assert all(counts[table] > 0 for table in counts)
    assert {row[0] for row in quote_rows} == {"lol-ktc-sgw-2026-06-15-game2"}
    assert {row[1] for row in quote_rows} == {2}
    assert {row[2] for row in quote_rows} == {
        "KT Rolster Challengers",
        "Saigon Warriors",
    }
    assert {row[3] for row in quote_rows} == {"ok"}
