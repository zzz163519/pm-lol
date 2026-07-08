from __future__ import annotations

import json
from typing import Any

from pm_lol.models import Market, QuoteSnapshot


class PolymarketClient:
    def __init__(
        self,
        gamma_base_url: str = "https://gamma-api.polymarket.com",
        clob_base_url: str = "https://clob.polymarket.com",
    ) -> None:
        self.gamma_base_url = gamma_base_url.rstrip("/")
        self.clob_base_url = clob_base_url.rstrip("/")

    def get_market(self, market_id: str) -> dict[str, Any]:
        import requests

        response = requests.get(f"{self.gamma_base_url}/markets/{market_id}", timeout=20)
        response.raise_for_status()
        return response.json()

    def search_markets(self, keywords: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        import requests

        markets_by_id: dict[str, dict[str, Any]] = {}
        for keyword in keywords:
            response = requests.get(
                f"{self.gamma_base_url}/markets",
                params={"search": keyword},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            markets = payload.get("markets", payload) if isinstance(payload, dict) else payload
            for market in markets:
                market_id = str(market.get("id") or market.get("market_id") or market.get("conditionId"))
                markets_by_id[market_id] = market
        return list(markets_by_id.values())

    def get_orderbook(self, token_id: str) -> dict[str, Any]:
        import requests

        response = requests.get(
            f"{self.clob_base_url}/book",
            params={"token_id": token_id},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


def parse_market(payload: dict[str, Any]) -> Market:
    market_payload = payload.get("selectedMarket", payload)
    event_payload = payload.get("event", {})
    outcomes = _loads_json_array(market_payload["outcomes"])
    token_ids = _loads_json_array(market_payload["clobTokenIds"])

    raw = dict(payload)
    for key in ("startTime", "startDate", "startDateIso", "endTime", "endDate"):
        if key not in raw and event_payload.get(key) is not None:
            raw[key] = event_payload[key]

    return Market(
        market_id=str(market_payload["id"]),
        condition_id=market_payload["conditionId"],
        question_id=market_payload.get("questionID"),
        event_id=str(event_payload["id"]) if event_payload.get("id") is not None else None,
        event_slug=event_payload.get("slug"),
        slug=market_payload["slug"],
        title=market_payload.get("question") or market_payload.get("title") or "",
        market_type=_infer_market_type(market_payload),
        outcomes=[str(outcome) for outcome in outcomes],
        token_ids=[str(token_id) for token_id in token_ids],
        volume=_float_or_none(market_payload.get("volume", event_payload.get("volume"))),
        liquidity=_float_or_none(market_payload.get("liquidity", event_payload.get("liquidity"))),
        active=bool(market_payload.get("active", False)),
        closed=bool(market_payload.get("closed", False)),
        raw=raw,
    )


def parse_orderbooks(payload: list[dict[str, Any]] | dict[str, Any]) -> list[QuoteSnapshot]:
    books = payload if isinstance(payload, list) else [payload]
    return [_parse_orderbook(book) for book in books]


def _parse_orderbook(book: dict[str, Any]) -> QuoteSnapshot:
    bids = list(book.get("bids", []))
    asks = list(book.get("asks", []))
    best_bid = max((_float_or_none(level.get("price")) for level in bids), default=None)
    best_ask = min((_float_or_none(level.get("price")) for level in asks), default=None)
    spread = round(best_ask - best_bid, 10) if best_bid is not None and best_ask is not None else None

    return QuoteSnapshot(
        condition_id=book["market"],
        token_id=str(book["asset_id"]),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        bid_depth=sum(_float_or_none(level.get("size")) or 0.0 for level in bids),
        ask_depth=sum(_float_or_none(level.get("size")) or 0.0 for level in asks),
        bid_count=len(bids),
        ask_count=len(asks),
        timestamp_ms=int(book["timestamp"]) if book.get("timestamp") is not None else None,
        bids=bids,
        asks=asks,
        raw=book,
    )


def _loads_json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON array")
    return parsed


def _infer_market_type(market_payload: dict[str, Any]) -> str:
    text = " ".join(
        str(market_payload.get(key, ""))
        for key in ("slug", "question", "title", "groupItemTitle")
    ).lower()
    return "game_winner" if "game" in text and "winner" in text else "unknown"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
