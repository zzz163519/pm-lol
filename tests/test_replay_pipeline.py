import sqlite3

from pm_lol.replay_pipeline import run_replay
from pm_lol.storage import SCHEMA_VERSION


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


def test_run_replay_generates_report_from_collector_run_events(tmp_path):
    db_path = tmp_path / "replay.db"
    report_path = tmp_path / "replay-report.md"

    summary = run_replay(db_path, report_path=report_path)

    assert summary["schema_version"] == SCHEMA_VERSION
    assert summary["report_path"] == str(report_path)
    assert summary["source_status_summary"]["ok"] >= 1
    assert summary["source_status_summary"]["skipped_low_confidence"] == 1
    assert summary["source_status_summary"]["stale"] == 1
    assert summary["source_status_summary"]["rate_limited"] == 1
    assert summary["collector_events"] >= 4

    report = report_path.read_text()
    assert "# PM-LOL Phase 1 Replay Report" in report
    assert f"Schema version: `{SCHEMA_VERSION}`" in report
    assert "mappingConfidence" in report
    assert "Quote timeline" in report
    assert "Game state timeline" in report
    assert "Source status timeline" in report
    assert "skipped_low_confidence" in report
    assert "rate_limited" in report
    assert "No fair probability, edge, signal, paper trading, wallet, or order output." in report

    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM collector_runs").fetchone()[0]

    assert row_count == summary["collector_events"]
