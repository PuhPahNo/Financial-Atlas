"""Headline-backtest refresh job (PRD model-lab).

Re-runs the standard 3-year headline backtest for every active strategy and persists
the result onto the strategy card (``metrics_json["_backtest"]``), so the Models grid
shows numbers produced by the current engine — not stale runs from before an engine
change. One strategy at a time (the engine serializes anyway); a failure on one model
is recorded and skipped, never fatal.

Run after ``warm_prices`` so index-wide models read a warm store:
    python -m app.jobs.warm_prices && python -m app.jobs.refresh_headlines
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from ..db import init_db, session_scope
from ..models.paper_trading import TradingStrategy
from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest

log = logging.getLogger("jobs.refresh_headlines")


def run(*, years: int = 3) -> dict:
    init_db()
    service.ensure_seeded()
    end = date.today()
    start = end - timedelta(days=round(365.25 * years))
    with session_scope() as s:
        targets = [(r.id, r.name) for r in
                   s.query(TradingStrategy).filter_by(status="active").order_by(TradingStrategy.id).all()]

    refreshed: list[str] = []
    failed: list[dict] = []
    for strategy_id, name in targets:
        try:
            service.run_backtest(BacktestRequest(
                strategy_id=strategy_id, start_date=start, end_date=end,
                starting_cash=100000.0, benchmark="SPY", persist_headline=True,
            ))
            refreshed.append(name)
            log.info("headline refreshed: %s", name)
        except Exception as exc:  # noqa: BLE001 — one bad model must not sink the sweep
            failed.append({"strategy": name, "error": str(exc)})
            log.warning("headline refresh failed for %s: %s", name, exc)

    result = {"window": {"start": start.isoformat(), "end": end.isoformat()},
              "strategies": len(targets), "refreshed": len(refreshed), "failed": failed}
    log.info("headline refresh complete: %s", {**result, "failed": len(failed)})
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
