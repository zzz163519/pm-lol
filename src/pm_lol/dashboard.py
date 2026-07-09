from __future__ import annotations

import argparse
import html
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pm_lol.storage import SCHEMA_VERSION, SQLiteStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "replay.db"
STATUS_PRIORITY = (
    "stale",
    "rate_limited",
    "missing",
    "no_liquidity",
    "low_confidence",
)


def build_dashboard_snapshot(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    match_id: str | None = None,
    game_id: str | None = None,
    source: str | None = None,
    observed_from: str | None = None,
    observed_to: str | None = None,
    fixture_mode: bool = False,
) -> dict[str, Any]:
    storage = SQLiteStorage(db_path)
    filters = {
        "matchId": match_id,
        "gameId": game_id,
        "source": source,
        "observedFrom": observed_from,
        "observedTo": observed_to,
        "fixtureMode": fixture_mode,
    }
    markets = _dashboard_markets(
        storage.path,
        match_id=match_id,
        game_id=game_id,
        observed_from=observed_from,
        observed_to=observed_to,
        fixture_mode=fixture_mode,
    )
    game_states = _game_states(
        storage.path,
        match_id=match_id,
        game_id=game_id,
        observed_from=observed_from,
        observed_to=observed_to,
        fixture_mode=fixture_mode,
    )
    picks = (
        _picks(storage.path, match_id=match_id, game_id=game_id)
        if fixture_mode or game_states
        else {"blue": [], "red": []}
    )
    collector_events = _collector_events(storage.path, source=source)
    status_summary = _source_status_summary(markets, game_states, collector_events)
    if not markets or not game_states:
        status_summary["missing"] = status_summary.get("missing", 0) + 1

    return {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotMode": "fixture" if fixture_mode else "current",
        "filters": filters,
        "markets": markets,
        "gameStates": game_states,
        "picks": picks,
        "collectorEvents": collector_events,
        "sourceStatusSummary": dict(sorted(status_summary.items())),
        "readOnlyGuards": {
            "fairProbability": "disabled",
            "polymarketOrders": "disabled",
            "strategySignals": "disabled",
        },
    }


def render_dashboard_html(snapshot: dict[str, Any]) -> str:
    markets = snapshot["markets"]
    game_states = snapshot["gameStates"]
    picks = snapshot["picks"]
    status_summary = snapshot["sourceStatusSummary"]
    collector_events = snapshot["collectorEvents"]

    market_rows = "\n".join(_market_row(market) for market in markets)
    if not market_rows:
        market_rows = """
        <tr>
          <td colspan="8" class="empty">missing market mapping or quote snapshot</td>
        </tr>
        """

    game_cards = "\n".join(_game_state_card(row) for row in game_states)
    if not game_cards:
        game_cards = '<section class="panel"><h2>Game state</h2><p class="empty">missing game state snapshot</p></section>'

    status_badges = " ".join(_badge(status, str(count)) for status, count in status_summary.items())
    if not status_badges:
        status_badges = _badge("missing", "0")

    event_rows = "\n".join(
        "<tr>"
        f"<td>{_e(event['observedAt'])}</td>"
        f"<td>{_e(event['source'])}</td>"
        f"<td>{_e(event['target'])}</td>"
        f"<td>{_badge(event['sourceStatus'])}</td>"
        f"<td>{_e(event['errorCode'])}</td>"
        "</tr>"
        for event in collector_events
    )
    if not event_rows:
        event_rows = '<tr><td colspan="5" class="empty">missing collector status events</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PM-LOL Read-only Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --surface: #ffffff;
      --line: #d8dde6;
      --text: #111827;
      --muted: #5b6472;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --neutral: #4b5563;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      line-height: 1.2;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      line-height: 1.3;
    }}
    .subtle {{ color: var(--muted); font-size: 13px; }}
    .guardrail {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.9fr);
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 10px 8px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-weight: 650;
      background: #fbfcfd;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-height: 72px;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .metric .value {{
      font-size: 18px;
      font-weight: 700;
      line-height: 1.25;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      color: var(--neutral);
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }}
    .badge.ok, .badge.fresh, .badge.final {{ border-color: #99d8c9; color: var(--accent); background: #edfdf8; }}
    .badge.low_confidence, .badge.stale, .badge.no_liquidity {{ border-color: #f4c780; color: var(--warn); background: #fffbeb; }}
    .badge.rate_limited, .badge.missing, .badge.error, .badge.parse_error, .badge.network_error {{ border-color: #fca5a5; color: var(--bad); background: #fef2f2; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .empty {{ color: var(--bad); font-weight: 650; }}
    .picks {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .pick-list {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
    }}
    .pick-list h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .pick-list ul {{
      margin: 0;
      padding-left: 18px;
    }}
    @media (max-width: 900px) {{
      main {{ padding: 16px; }}
      header, .layout {{ display: block; }}
      .guardrail {{ justify-content: flex-start; margin-top: 10px; }}
      .metric-grid, .picks {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>PM-LOL Read-only Dashboard</h1>
        <div class="subtle">Schema {_e(snapshot['schemaVersion'])} · SQLite snapshots only</div>
      </div>
      <div class="guardrail">
        {_badge("Fair probability: disabled")}
        {_badge("Polymarket orders: disabled")}
        {_badge("Strategy signals: disabled")}
      </div>
    </header>

    <section class="panel">
      <h2>Source status</h2>
      <div class="badges">{status_badges}</div>
    </section>

    <div class="layout">
      <section class="panel">
        <h2>Market mapping and quotes</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Match / Game</th>
                <th>Market</th>
                <th>mappingConfidence</th>
                <th>Yes bestBid / bestAsk</th>
                <th>No bestBid / bestAsk</th>
                <th>Status</th>
                <th>sampleAgeSeconds</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>{market_rows}</tbody>
          </table>
        </div>
      </section>

      <div>
        {game_cards}
        <section class="panel">
          <h2>Picks</h2>
          <div class="picks">
            <div class="pick-list"><h3>Blue</h3>{_pick_list(picks['blue'])}</div>
            <div class="pick-list"><h3>Red</h3>{_pick_list(picks['red'])}</div>
          </div>
        </section>
      </div>
    </div>

    <section class="panel">
      <h2>Collector timeline</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Observed</th><th>Source</th><th>Target</th><th>Status</th><th>Error</th></tr>
          </thead>
          <tbody>{event_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def serve_dashboard(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> None:
    db_path = Path(db_path)

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = _request_filters(parsed.query)
            if parsed.path == "/api/dashboard":
                snapshot = build_dashboard_snapshot(db_path, **params)
                self._send_json(snapshot)
                return
            if parsed.path in {"/", "/dashboard"}:
                snapshot = build_dashboard_snapshot(db_path, **params)
                self._send_html(render_dashboard_html(snapshot))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, body: dict[str, Any]) -> None:
            data = json.dumps(body, indent=2, sort_keys=True).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, body: str) -> None:
            data = body.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Serving PM-LOL dashboard at http://{host}:{port}/ from {db_path}", flush=True)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only PM-LOL dashboard.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite snapshot database path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    serve_dashboard(args.db, host=args.host, port=args.port)
    return 0


def _dashboard_markets(
    db_path: Path,
    *,
    match_id: str | None,
    game_id: str | None,
    observed_from: str | None,
    observed_to: str | None,
    fixture_mode: bool,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[object] = []
    if match_id:
        clauses.append("rm.match_id = ?")
        params.append(match_id)
    if game_id:
        clauses.append("rm.game_id = ?")
        params.append(game_id)
    if not fixture_mode:
        clauses.append("rm.mapping_confidence >= 0.9")
        clauses.append("rm.market_status NOT LIKE 'skipped%'")
        clauses.append("m.active = 1")
        clauses.append("m.closed = 0")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                rm.market_id, rm.condition_id, rm.match_id, rm.game_id,
                rm.game_number, rm.mapping_confidence, rm.market_status,
                rm.skip_reason, rm.yes_token_id, rm.no_token_id,
                rm.team_a_name, rm.team_b_name, rm.blue_team_id, rm.red_team_id,
                m.slug AS market_slug, m.title AS market_title,
                m.event_slug, m.liquidity, mt.league, mt.start_time
            FROM resolved_markets rm
            JOIN markets m ON m.market_id = rm.market_id
            LEFT JOIN matches mt ON mt.match_id = rm.match_id
            {where}
            ORDER BY mt.start_time ASC, rm.match_id ASC, rm.game_number ASC
            """,
            params,
        ).fetchall()

    return [
        _market_view(
            dict(row),
            yes_quote=_latest_quote(
                db_path,
                condition_id=row["condition_id"],
                token_id=row["yes_token_id"],
                observed_from=observed_from,
                observed_to=observed_to,
            ),
            no_quote=_latest_quote(
                db_path,
                condition_id=row["condition_id"],
                token_id=row["no_token_id"],
                observed_from=observed_from,
                observed_to=observed_to,
            ),
        )
        for row in rows
    ]


def _market_view(
    row: dict[str, Any],
    *,
    yes_quote: dict[str, Any] | None,
    no_quote: dict[str, Any] | None,
) -> dict[str, Any]:
    badges = []
    if row["mapping_confidence"] < 0.9 or row["market_status"] == "skipped_low_confidence":
        badges.append("low_confidence")
    for quote in (yes_quote, no_quote):
        if quote is None:
            badges.append("missing")
        elif quote["sourceStatus"] in {"stale", "rate_limited", "no_liquidity"}:
            badges.append(quote["sourceStatus"])
        elif quote["bestBid"] is None or quote["bestAsk"] is None:
            badges.append("no_liquidity")
    return {
        "marketId": row["market_id"],
        "conditionId": row["condition_id"],
        "matchId": row["match_id"],
        "gameId": row["game_id"],
        "gameNumber": row["game_number"],
        "league": row["league"],
        "marketSlug": row["market_slug"],
        "marketTitle": row["market_title"],
        "teams": {
            "a": row["team_a_name"],
            "b": row["team_b_name"],
            "blueTeamId": row["blue_team_id"],
            "redTeamId": row["red_team_id"],
        },
        "mappingConfidence": row["mapping_confidence"],
        "marketStatus": row["market_status"],
        "skipReason": row["skip_reason"],
        "yesQuote": yes_quote or _missing_quote(row["yes_token_id"]),
        "noQuote": no_quote or _missing_quote(row["no_token_id"]),
        "statusBadges": _ordered_unique(badges or ["ok"]),
    }


def _latest_quote(
    db_path: Path,
    *,
    condition_id: str,
    token_id: str,
    observed_from: str | None,
    observed_to: str | None,
) -> dict[str, Any] | None:
    clauses = ["condition_id = ?", "token_id = ?"]
    params: list[object] = [condition_id, token_id]
    if observed_from:
        clauses.append("observed_at >= ?")
        params.append(observed_from)
    if observed_to:
        clauses.append("observed_at <= ?")
        params.append(observed_to)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT token_id, outcome, best_bid, best_ask, spread, bid_depth,
                   ask_depth, bid_count, ask_count, observed_at, source_status,
                   error_code
            FROM quotes
            WHERE {' AND '.join(clauses)}
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    if row is None:
        return None
    return {
        "tokenId": row["token_id"],
        "outcome": row["outcome"],
        "bestBid": row["best_bid"],
        "bestAsk": row["best_ask"],
        "spread": row["spread"],
        "bidDepth": row["bid_depth"],
        "askDepth": row["ask_depth"],
        "bidCount": row["bid_count"],
        "askCount": row["ask_count"],
        "observedAt": row["observed_at"],
        "sampleAgeSeconds": None,
        "sourceStatus": row["source_status"],
        "errorCode": row["error_code"],
    }


def _missing_quote(token_id: str) -> dict[str, Any]:
    return {
        "tokenId": token_id,
        "outcome": None,
        "bestBid": None,
        "bestAsk": None,
        "spread": None,
        "bidDepth": 0,
        "askDepth": 0,
        "bidCount": 0,
        "askCount": 0,
        "observedAt": None,
        "sampleAgeSeconds": None,
        "sourceStatus": "missing",
        "errorCode": "missing_quote",
    }


def _game_states(
    db_path: Path,
    *,
    match_id: str | None,
    game_id: str | None,
    observed_from: str | None,
    observed_to: str | None,
    fixture_mode: bool,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[object] = []
    if match_id:
        clauses.append("g.match_id = ?")
        params.append(match_id)
    if game_id:
        clauses.append("s.game_id = ?")
        params.append(game_id)
    if observed_from:
        clauses.append("s.observed_at >= ?")
        params.append(observed_from)
    if observed_to:
        clauses.append("s.observed_at <= ?")
        params.append(observed_to)
    if not fixture_mode:
        clauses.append("g.state IN ('in_game', 'inProgress', 'in_progress', 'live')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                s.game_id, g.match_id, g.game_number, s.source_timestamp,
                s.observed_at, s.game_clock, s.game_state, s.blue_gold,
                s.red_gold, s.gold_diff, s.blue_towers, s.red_towers,
                s.blue_dragons_json, s.red_dragons_json, s.blue_barons,
                s.red_barons, s.blue_kills, s.red_kills, s.paused,
                s.finished, s.winner, s.source_status, s.sample_age_seconds,
                s.error_code, s.source, s.raw_json
            FROM game_state_snapshots s
            JOIN games g ON g.game_id = s.game_id
            {where}
            ORDER BY s.observed_at DESC, s.source_timestamp DESC
            LIMIT 20
            """,
            params,
        ).fetchall()
    game_states = []
    for row in rows:
        raw = json.loads(row["raw_json"])
        numeric_available = _live_numeric_stats_available(row, raw)
        game_state = {
            "gameId": row["game_id"],
            "matchId": row["match_id"],
            "gameNumber": row["game_number"],
            "sourceTimestamp": row["source_timestamp"],
            "observedAt": row["observed_at"],
            "gameClock": row["game_clock"] if numeric_available else None,
            "gameState": row["game_state"],
            "gold": {
                "blue": row["blue_gold"] if numeric_available else None,
                "red": row["red_gold"] if numeric_available else None,
                "diff": row["gold_diff"] if numeric_available else None,
            },
            "objectives": {
                "blueTowers": row["blue_towers"] if numeric_available else None,
                "redTowers": row["red_towers"] if numeric_available else None,
                "blueDragons": json.loads(row["blue_dragons_json"]) if numeric_available else [],
                "redDragons": json.loads(row["red_dragons_json"]) if numeric_available else [],
                "blueBarons": row["blue_barons"] if numeric_available else None,
                "redBarons": row["red_barons"] if numeric_available else None,
                "blueKills": row["blue_kills"] if numeric_available else None,
                "redKills": row["red_kills"] if numeric_available else None,
            },
            "paused": None if row["paused"] is None else bool(row["paused"]),
            "finished": bool(row["finished"]),
            "winner": row["winner"],
            "sourceStatus": row["source_status"],
            "sampleAgeSeconds": row["sample_age_seconds"],
            "errorCode": row["error_code"],
            "source": row["source"],
            "citoStatus": raw.get("status") or row["source_status"],
            "citoReason": raw.get("reason"),
            "citoConfidence": raw.get("confidence"),
            "dataQuality": raw.get("dataQuality"),
            "liveNumericStatsAvailable": numeric_available,
        }
        game_states.append(game_state)
    return game_states


def _live_numeric_stats_available(row: sqlite3.Row, raw: dict[str, Any]) -> bool:
    if row["error_code"] == "live_numeric_stats_unavailable":
        return False
    if row["source_status"] in {"on_break", "stale"}:
        return False
    if str(raw.get("status") or "").lower() in {"on_break", "stale"}:
        return False
    data_quality = raw.get("dataQuality")
    if isinstance(data_quality, dict):
        value = data_quality.get("numericLiveStats") or data_quality.get("numeric_live_stats")
        if str(value or "").lower() == "unavailable":
            return False
    confidence = raw.get("confidence")
    if not isinstance(confidence, dict):
        return True
    values = [confidence.get(key) for key in ("gold", "kills", "objectives", "timer") if key in confidence]
    return not (values and all(value == 0 for value in values))


def _picks(db_path: Path, *, match_id: str | None, game_id: str | None) -> dict[str, list[str]]:
    clauses: list[str] = []
    params: list[object] = []
    if match_id:
        clauses.append("match_id = ?")
        params.append(match_id)
    if game_id:
        clauses.append("game_id = ?")
        params.append(game_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT team_side, champion_id, participant_id
            FROM draft_snapshots
            {where}
            ORDER BY team_side ASC, participant_id ASC
            """,
            params,
        ).fetchall()
    picks = {"blue": [], "red": []}
    for row in rows:
        side = row["team_side"]
        if side in picks:
            picks[side].append(row["champion_id"])
    return picks


def _collector_events(db_path: Path, *, source: str | None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[object] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT observed_at, collector_name, source, target, outcome,
                   source_status, error_code, budget_state_json
            FROM collector_runs
            {where}
            ORDER BY observed_at DESC, run_id DESC
            LIMIT 50
            """,
            params,
        ).fetchall()
    return [
        {
            "observedAt": row["observed_at"],
            "collectorName": row["collector_name"],
            "source": row["source"],
            "target": row["target"],
            "outcome": row["outcome"],
            "sourceStatus": row["source_status"],
            "errorCode": row["error_code"],
            "budgetState": json.loads(row["budget_state_json"]),
        }
        for row in rows
    ]


def _source_status_summary(
    markets: list[dict[str, Any]],
    game_states: list[dict[str, Any]],
    collector_events: list[dict[str, Any]],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    for market in markets:
        for badge in market["statusBadges"]:
            summary[badge] = summary.get(badge, 0) + 1
        for quote_key in ("yesQuote", "noQuote"):
            status = market[quote_key]["sourceStatus"]
            summary[status] = summary.get(status, 0) + 1
    for row in game_states:
        status = row["sourceStatus"]
        summary[status] = summary.get(status, 0) + 1
    for event in collector_events:
        status = event["sourceStatus"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def _market_row(market: dict[str, Any]) -> str:
    yes = market["yesQuote"]
    no = market["noQuote"]
    latest_observed = yes["observedAt"] or no["observedAt"]
    sample_age = yes["sampleAgeSeconds"] if yes["sampleAgeSeconds"] is not None else no["sampleAgeSeconds"]
    badges = " ".join(_badge(status) for status in market["statusBadges"])
    return f"""
    <tr>
      <td>{_e(market['matchId'])}<br><span class="subtle">Game {_e(market['gameNumber'])}</span></td>
      <td>{_e(market['marketTitle'])}<br><span class="subtle">{_e(yes['outcome'])} vs {_e(no['outcome'])}</span></td>
      <td>{_fmt_float(market['mappingConfidence'], 4)}</td>
      <td>{_quote_cell(yes)}</td>
      <td>{_quote_cell(no)}</td>
      <td><div class="badges">{badges}</div></td>
      <td>{_e(sample_age)}</td>
      <td>{_e(latest_observed)}</td>
    </tr>
    """


def _game_state_card(row: dict[str, Any]) -> str:
    objectives = row["objectives"]
    numeric_notice = ""
    if not row.get("liveNumericStatsAvailable", True):
        numeric_notice = (
            '<p class="empty">live numeric stats unavailable'
            f" · {_e(row.get('citoStatus'))}"
            f" · {_e(row.get('citoReason'))}</p>"
        )
    return f"""
    <section class="panel">
      <h2>Game state</h2>
      {numeric_notice}
      <div class="metric-grid">
        <div class="metric"><div class="label">Game clock</div><div class="value">{_fmt_clock(row['gameClock'])}</div></div>
        <div class="metric"><div class="label">State</div><div class="value">{_e(row['gameState'])}</div></div>
        <div class="metric"><div class="label">Gold</div><div class="value">{_fmt_int(row['gold']['blue'])} / {_fmt_int(row['gold']['red'])}</div><div class="subtle">Diff {_fmt_int(row['gold']['diff'])}</div></div>
        <div class="metric"><div class="label">Kills</div><div class="value">{_fmt_int(objectives['blueKills'])} / {_fmt_int(objectives['redKills'])}</div></div>
        <div class="metric"><div class="label">Towers</div><div class="value">{_fmt_int(objectives['blueTowers'])} / {_fmt_int(objectives['redTowers'])}</div></div>
        <div class="metric"><div class="label">Dragons</div><div class="value">{_e(', '.join(objectives['blueDragons']) or 'none')} / {_e(', '.join(objectives['redDragons']) or 'none')}</div></div>
        <div class="metric"><div class="label">Barons</div><div class="value">{_fmt_int(objectives['blueBarons'])} / {_fmt_int(objectives['redBarons'])}</div></div>
        <div class="metric"><div class="label">CITO status / sampleAgeSeconds</div><div class="value">{_badge(row.get('citoStatus') or row['sourceStatus'])}</div><div class="subtle">{_e(row['sampleAgeSeconds'])}</div></div>
      </div>
    </section>
    """


def _request_filters(query: str) -> dict[str, str | None]:
    params = parse_qs(query)
    return {
        "match_id": _first(params, "matchId") or _first(params, "match_id"),
        "game_id": _first(params, "gameId") or _first(params, "game_id"),
        "source": _first(params, "source"),
        "observed_from": _first(params, "observedFrom") or _first(params, "observed_from"),
        "observed_to": _first(params, "observedTo") or _first(params, "observed_to"),
        "fixture_mode": _truthy(_first(params, "fixtureMode") or _first(params, "fixture_mode")),
    }


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key) or []
    return values[0] if values and values[0] else None


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "fixture", "dev"}


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ordered_unique(statuses: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for status in [*STATUS_PRIORITY, *statuses]:
        if status in statuses and status not in seen:
            ordered.append(status)
            seen.add(status)
    return ordered


def _quote_cell(quote: dict[str, Any]) -> str:
    return (
        f"{_fmt_float(quote['bestBid'], 3)} / {_fmt_float(quote['bestAsk'], 3)}"
        f"<br>{_badge(quote['sourceStatus'])}"
    )


def _pick_list(items: list[str]) -> str:
    if not items:
        return '<p class="empty">missing</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def _badge(label: str, value: str | None = None) -> str:
    text = label if value is None else f"{label}: {value}"
    return f'<span class="badge {_class_name(label)}">{_e(text)}</span>'


def _class_name(label: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label.lower())


def _fmt_float(value: float | None, digits: int) -> str:
    return "missing" if value is None else f"{value:.{digits}f}"


def _fmt_int(value: int | None) -> str:
    return "missing" if value is None else f"{value:,}"


def _fmt_clock(value: float | None) -> str:
    if value is None:
        return "missing"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes}:{seconds:02d}"


def _e(value: object) -> str:
    if value is None:
        return "missing"
    return html.escape(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
