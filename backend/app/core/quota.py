"""Daily call budgets for keyed free-tier providers (PRD free-data-pipeline).

FMP's free tier allows ~250 requests/day; burning it on background enrichment means
mover/quote requests start failing by mid-session. This module keeps a per-provider,
per-day counter (persisted via the filesystem cache so restarts don't reset it) and
the provider refuses to spend past its budget — raising ``RateLimitError`` so the
fallback chain degrades to keyless sources (Yahoo, Stooq, Finnhub) instead of
exhausting the key. Only real network calls count; cache hits are free.
"""
from __future__ import annotations

import threading
from datetime import date

from . import cache

_LOCK = threading.Lock()
_DAY_SECONDS = 86400


def _key(provider: str) -> str:
    return f"{provider}:{date.today().isoformat()}"


def spent(provider: str) -> int:
    """Calls recorded for ``provider`` today."""
    try:
        return int(cache.peek("quota", _key(provider), _DAY_SECONDS) or 0)
    except (TypeError, ValueError):
        return 0


def spend(provider: str) -> int:
    """Record one call; returns today's new count."""
    with _LOCK:
        count = spent(provider) + 1
        cache.put("quota", _key(provider), count)
        return count


def available(provider: str, budget: int) -> bool:
    """True while today's spend is under ``budget`` (a budget of 0 disables the guard)."""
    if budget <= 0:
        return True
    return spent(provider) < budget
