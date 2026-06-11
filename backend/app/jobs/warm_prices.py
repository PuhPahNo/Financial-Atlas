"""Price-store + PIT-fundamentals warm job (PRD free-data-pipeline).

Fills the durable price store (adjusted daily closes) and the point-in-time
fundamentals table for the entire investable superset — the current S&P 500, every
name in the index change-log, and the bundled ETF universe. The first run downloads
each ticker's full history once (~1 provider call per ticker, throttled by the
shared token bucket); every later run appends only the missing tail, so a nightly
cron keeps decades of backtest data fresh for roughly one small request per ticker.

Run locally or as a Render Cron Job:  ``python -m app.jobs.warm_prices``
"""
from __future__ import annotations

import logging

from ..backtesting import universe as univ
from ..backtesting.screen import warm_universe_for_backtests
from ..db import init_db

log = logging.getLogger("jobs.warm_prices")


def run(*, years: int = 25, include_fundamentals: bool = True) -> dict:
    init_db()
    superset = univ.investable_superset()
    result = warm_universe_for_backtests(superset, years=years, include_fundamentals=include_fundamentals)
    log.info("price warm complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
