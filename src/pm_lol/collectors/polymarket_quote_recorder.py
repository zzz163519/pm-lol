from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from pm_lol.models import QuoteSnapshot
from pm_lol.sources.polymarket import parse_orderbooks
from pm_lol.storage import SQLiteStorage


class OrderbookClient(Protocol):
    def get_orderbook(self, token_id: str) -> dict: ...


@dataclass(frozen=True, slots=True)
class QuoteTarget:
    event_slug: str | None
    market_slug: str | None
    condition_id: str | None
    token_id: str | None
    outcome: str | None
    game_number: int | None = None


class PolymarketQuoteRecorder:
    def __init__(
        self,
        client: OrderbookClient,
        storage: SQLiteStorage,
        token_ids: Iterable[str | QuoteTarget],
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.storage = storage
        self.targets = [_coerce_target(token_id) for token_id in token_ids]
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep

    def run_once(self) -> dict[str, int]:
        quotes_written = 0
        skipped = 0
        errors = 0
        for target in self.targets:
            if not target.token_id:
                self.storage.insert_quote(_absent_quote(target))
                quotes_written += 1
                skipped += 1
                continue

            payload, error_code = self._get_orderbook(target.token_id)
            if error_code is not None:
                self.storage.insert_quote(_error_quote(target, error_code))
                quotes_written += 1
                errors += 1
                continue

            for quote in parse_orderbooks(payload):
                self.storage.insert_quote(_attach_target(quote, target))
                quotes_written += 1
        return {
            "tokens_seen": len(self.targets),
            "quotes_written": quotes_written,
            "skipped": skipped,
            "errors": errors,
        }

    def _get_orderbook(self, token_id: str) -> tuple[dict, str | None]:
        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.client.get_orderbook(token_id), None
            except Exception as exc:  # requests adapters expose several exception types.
                last_error = exc
                if attempt == self.max_attempts or not _is_retryable(exc):
                    break
                self.sleep(self.backoff_seconds * attempt)
        return {}, _error_code(last_error)


def _coerce_target(value: str | QuoteTarget) -> QuoteTarget:
    if isinstance(value, QuoteTarget):
        return value
    return QuoteTarget(
        event_slug=None,
        market_slug=None,
        condition_id=None,
        token_id=str(value),
        outcome=None,
    )


def _attach_target(quote: QuoteSnapshot, target: QuoteTarget) -> QuoteSnapshot:
    quote.event_slug = target.event_slug
    quote.market_slug = target.market_slug
    quote.condition_id = target.condition_id or quote.condition_id
    quote.token_id = target.token_id or quote.token_id
    quote.outcome = target.outcome
    quote.game_number = target.game_number
    quote.source_status = (
        "no_liquidity" if quote.bid_count == 0 and quote.ask_count == 0 else "ok"
    )
    return quote


def _absent_quote(target: QuoteTarget) -> QuoteSnapshot:
    return QuoteSnapshot(
        event_slug=target.event_slug,
        market_slug=target.market_slug,
        condition_id=target.condition_id,
        token_id=target.token_id,
        outcome=target.outcome,
        game_number=target.game_number,
        best_bid=None,
        best_ask=None,
        spread=None,
        bid_depth=0.0,
        ask_depth=0.0,
        source_status="absent",
        error_code="missing_market",
        raw={"reason": "missing_market"},
    )


def _error_quote(target: QuoteTarget, error_code: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        event_slug=target.event_slug,
        market_slug=target.market_slug,
        condition_id=target.condition_id,
        token_id=target.token_id,
        outcome=target.outcome,
        game_number=target.game_number,
        best_bid=None,
        best_ask=None,
        spread=None,
        bid_depth=0.0,
        ask_depth=0.0,
        source_status="error",
        error_code=error_code,
        raw={"error_code": error_code},
    )


def _is_retryable(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    return status_code == 429 or (isinstance(status_code, int) and 500 <= status_code <= 599)


def _error_code(exc: BaseException | None) -> str:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return f"http_{status_code}"
    return "network_error"
