"""Shared API response envelope helpers."""
from __future__ import annotations

from typing import Any


def envelope(
    data: Any,
    *,
    ticker: str | None = None,
    served_by: str | None = None,
    stale: bool = False,
    as_of: str | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    meta = {"ticker": ticker, "served_by": served_by, "stale": stale}
    if as_of is not None:
        meta["as_of"] = as_of
    if warnings:
        meta["warnings"] = warnings
    return {"data": data, "meta": meta}


def derived_envelope(data: Any, *, served_by: str | None = "derived") -> dict:
    """Envelope for paper-trading/backtest results derived inside Atlas."""
    return envelope(data, served_by=served_by)
