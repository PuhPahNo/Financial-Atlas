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
from datetime import date, datetime, timedelta, timezone

from ..db import init_db, session_scope
from ..models.paper_trading import BacktestEquityPoint, BacktestRun, BacktestTrade, TradingStrategy
from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest

log = logging.getLogger("jobs.refresh_headlines")

# Retention for stored runs: this job writes one full run (~750 equity points +
# trades) per strategy per night — unbounded, that fills the small Render disk.
_KEEP_RUNS_PER_STRATEGY = 25
_KEEP_DAYS = 30


def prune_runs(*, keep_per_strategy: int = _KEEP_RUNS_PER_STRATEGY, keep_days: int = _KEEP_DAYS) -> int:
    """Delete old BacktestRun rows (children bulk-deleted first).

    Keeps the newest ``keep_per_strategy`` runs per strategy, plus anything from the
    last ``keep_days`` days regardless of count. Returns the number of runs deleted."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=keep_days)
    doomed: list[int] = []
    with session_scope() as s:
        rows = s.query(BacktestRun.id, BacktestRun.strategy_id, BacktestRun.created_at) \
                .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc()).all()
        per_strategy: dict[int | None, int] = {}
        for rid, sid, created in rows:
            per_strategy[sid] = per_strategy.get(sid, 0) + 1
            if per_strategy[sid] <= keep_per_strategy:
                continue
            if created is not None:
                created_naive = created.replace(tzinfo=None) if created.tzinfo else created
                if created_naive >= cutoff:
                    continue
            doomed.append(rid)
        for i in range(0, len(doomed), 500):  # stay under SQLite's bind-variable cap
            chunk = doomed[i:i + 500]
            s.query(BacktestTrade).filter(BacktestTrade.run_id.in_(chunk)).delete(synchronize_session=False)
            s.query(BacktestEquityPoint).filter(BacktestEquityPoint.run_id.in_(chunk)).delete(synchronize_session=False)
            s.query(BacktestRun).filter(BacktestRun.id.in_(chunk)).delete(synchronize_session=False)
    if doomed:
        log.info("pruned %d old backtest runs", len(doomed))
    return len(doomed)


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
              "strategies": len(targets), "refreshed": len(refreshed), "failed": failed,
              "pruned_runs": prune_runs()}
    log.info("headline refresh complete: %s", {**result, "failed": len(failed)})
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(run())
