from __future__ import annotations

from typing import Iterable, Protocol

from pm_lol.sources.polymarket import parse_orderbooks
from pm_lol.storage import SQLiteStorage


class OrderbookClient(Protocol):
    def get_orderbook(self, token_id: str) -> dict: ...


class PolymarketQuoteRecorder:
    def __init__(
        self,
        client: OrderbookClient,
        storage: SQLiteStorage,
        token_ids: Iterable[str],
    ) -> None:
        self.client = client
        self.storage = storage
        self.token_ids = list(token_ids)

    def run_once(self) -> dict[str, int]:
        quotes_written = 0
        for token_id in self.token_ids:
            payload = self.client.get_orderbook(token_id)
            for quote in parse_orderbooks(payload):
                self.storage.insert_quote(quote)
                quotes_written += 1
        return {"tokens_seen": len(self.token_ids), "quotes_written": quotes_written}
