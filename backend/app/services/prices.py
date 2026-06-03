"""Price & quote service (PRD 11)."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from ..providers.base import Interval
from ..providers.registry import run_chain


def price_history(ticker: str, *, range: str = "1y", interval: str = "1d"):
    iv = Interval(interval) if interval in {i.value for i in Interval} else Interval.DAY
    bars, served_by = run_chain("prices", "get_price_history", ticker, range=range, interval=iv)
    return {"bars": [b.model_dump() for b in bars], "currency": "USD"}, served_by


def _epoch(day: date) -> int:
    return int(datetime.combine(day, time(0, 0), tzinfo=timezone.utc).timestamp())


def price_window(ticker: str, *, start: date, end: date, interval: str = "1d"):
    """True daily bars for an explicit historical window (no range downsampling)."""
    iv = Interval(interval) if interval in {i.value for i in Interval} else Interval.DAY
    bars, served_by = run_chain(
        "prices", "get_price_window", ticker,
        period1=_epoch(start), period2=_epoch(end), interval=iv,
    )
    return {"bars": [b.model_dump() for b in bars], "currency": "USD"}, served_by


def quote(ticker: str):
    q, served_by = run_chain("quote", "get_quote", ticker)
    return q, served_by
