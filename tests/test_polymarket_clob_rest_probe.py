import pytest

from scripts.polymarket_clob_rest_probe import select_market, summarize_book


def _event(active=True):
    return {
        "slug": "lol-a-b-2026-07-21",
        "markets": [
            {
                "slug": "lol-a-b-2026-07-21",
                "active": active,
                "closed": False,
                "acceptingOrders": True,
                "outcomes": '["A", "B"]',
                "clobTokenIds": '["1", "2"]',
            }
        ],
    }


def test_select_market_requires_explicit_active_outcome_token_mapping():
    assert select_market(_event(), None)["slug"] == "lol-a-b-2026-07-21"
    with pytest.raises(ValueError, match="not active"):
        select_market(_event(active=False), None)


def test_summarize_book_uses_price_extrema_not_payload_order():
    result = summarize_book(
        {
            "bids": [{"price": "0.40"}, {"price": "0.45"}],
            "asks": [{"price": "0.60"}, {"price": "0.55"}],
            "timestamp": "123",
        }
    )

    assert result == {
        "bestBid": 0.45,
        "bestAsk": 0.55,
        "bidCount": 2,
        "askCount": 2,
        "sourceTimestamp": "123",
    }
