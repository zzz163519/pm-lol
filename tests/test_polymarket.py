import json
from pathlib import Path

from pm_lol.sources.polymarket import parse_market, parse_orderbooks


FIXTURES = Path(__file__).resolve().parents[1] / "docs" / "source-spike"


def load_sample(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_parse_market_extracts_market_metadata():
    payload = load_sample("polymarket-market-sample.json")

    market = parse_market(payload)

    assert market.market_id == "2530922"
    assert market.condition_id == "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553"
    assert market.slug == "lol-ktc-sgw-2026-06-15-game2"
    assert market.outcomes == ["KT Rolster Challengers", "Saigon Warriors"]
    assert market.token_ids[0].startswith("1001728148467465")
    assert market.volume == 74955.37260799993
    assert market.market_type == "game_winner"


def test_parse_orderbooks_extracts_quote_snapshots():
    payload = load_sample("polymarket-orderbook-sample.json")

    quotes = parse_orderbooks(payload)
    quote = next(q for q in quotes if q.token_id.startswith("1001728148467465"))

    assert quote.condition_id == "0x56243f448198c358a8f70d69f44091949ba1b260ae832793aab1c54ad8e00553"
    assert quote.best_bid == 0.791
    assert quote.best_ask == 0.801
    assert quote.spread == 0.01
    assert quote.bid_depth > 0
    assert quote.ask_depth > 0
    assert quote.timestamp_ms == 1781508217535
