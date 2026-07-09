"""Price-store + PIT-fundamentals warm job (PRD free-data-pipeline).

Fills the durable price store (adjusted daily closes) and the point-in-time
fundamentals table for the entire investable superset — the current S&P 500, every
name in the index change-log, and the bundled ETF universe. The first run downloads
each ticker's full history once (~1 provider call per ticker, throttled by the
shared token bucket); every later run appends only the missing tail, so a nightly
cron keeps decades of backtest data fresh for roughly one small request per ticker.

Production calls this from the in-process nightly maintenance loop. It can also
be run manually: ``python -m app.jobs.warm_prices``.
"""
from __future__ import annotations

import logging
import math
from datetime import date

from ..backtesting import universe as univ
from ..backtesting.screen import warm_universe_for_backtests
from ..db import init_db

log = logging.getLogger("jobs.warm_prices")


def _deep_refresh_rotation(count: int) -> int:
    """Full-refetch a rotating slice of stored tickers each run.

    The tail-merge overlap check only sees recent bars, so small dividend
    re-basings in OLD bars can't be detected incrementally — a periodic full
    refetch is the only repair. With count=60 the whole ~560-ticker store heals
    in about 10 nightly runs, at one cheap provider call per ticker."""
    if count <= 0:
        return 0
    from ..services import price_store
    tickers = price_store.stored_tickers()
    if not tickers:
        return 0
    chunks = max(1, math.ceil(len(tickers) / count))
    idx = date.today().toordinal() % chunks
    batch = tickers[idx * count:(idx + 1) * count]
    refreshed = sum(1 for tk in batch if price_store.deep_refresh(tk))
    log.info("deep refresh rotation: slice %d/%d, %d/%d refreshed", idx + 1, chunks, refreshed, len(batch))
    return refreshed


def run(*, years: int = 25, include_fundamentals: bool = True, deep_refresh_count: int = 60) -> dict:
    init_db()
    superset = univ.investable_superset()
    result = warm_universe_for_backtests(superset, years=years, include_fundamentals=include_fundamentals)
    result["deep_refreshed"] = _deep_refresh_rotation(deep_refresh_count)
    log.info("price warm complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
