from __future__ import annotations

from typing import Iterable, Protocol

from pm_lol.sources.polymarket import parse_market
from pm_lol.storage import SQLiteStorage


DEFAULT_KEYWORDS = ("lol", "lck", "lpl", "lec", "worlds")


class MarketSearchClient(Protocol):
    def search_markets(self, keywords: Iterable[str]) -> list[dict]: ...


class PolymarketMarketCollector:
    def __init__(
        self,
        client: MarketSearchClient,
        storage: SQLiteStorage,
        keywords: Iterable[str] = DEFAULT_KEYWORDS,
    ) -> None:
        self.client = client
        self.storage = storage
        self.keywords = tuple(keywords)
        self.active_token_ids: list[str] = []

    def run_once(self) -> dict[str, int]:
        payloads = self.client.search_markets(self.keywords)
        markets_seen = 0
        markets_written = 0
        active_token_ids: list[str] = []

        for payload in payloads:
            markets_seen += 1
            market = parse_market(payload)
            if market.market_type != "game_winner" or market.closed:
                continue
            self.storage.upsert_market(market)
            markets_written += 1
            if market.active:
                active_token_ids.extend(market.token_ids)

        self.active_token_ids = active_token_ids
        return {
            "markets_seen": markets_seen,
            "markets_written": markets_written,
            "active_token_ids": len(active_token_ids),
        }
