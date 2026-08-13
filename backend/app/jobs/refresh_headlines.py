"""Headline-backtest refresh job (PRD model-lab).

Re-runs the standard 3-year headline backtest for every active strategy and persists
the result onto the strategy card (``metrics_json["_backtest"]``), so the Models grid
shows numbers produced by the current engine — not stale runs from before an engine
change. One strategy at a time (the engine serializes anyway); a failure on one model
is recorded and skipped, never fatal.

Production runs each strategy in a fresh maintenance child so the large Python heap
from one index-wide model is returned to the OS before the next model starts. The
``run`` entry point remains useful for local/manual refreshes where more memory is
available.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from ..core import market_hours
from ..core.config import settings
from ..db import init_db, session_scope
from ..models.paper_trading import BacktestEquityPoint, BacktestRun, BacktestTrade, TradingStrategy
from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest

log = logging.getLogger("jobs.refresh_headlines")

# Retention for stored runs: this job writes one full run (~750 equity points +
# trades) per strategy per night — unbounded, that fills the small Render disk.
_KEEP_RUNS_PER_STRATEGY = 25
_KEEP_DAYS = 30


def _window(years: int) -> tuple[date, date]:
    maximum_years = max(1, settings.backtest_max_window_days // 365)
    if years < 1 or years > maximum_years:
        raise ValueError(f"years must be between 1 and {maximum_years}")
    end = market_hours.last_completed_trading_day()
    return end - timedelta(days=round(365.25 * years)), end


def active_targets() -> list[tuple[int, str]]:
    """Return the active strategy IDs/names in stable refresh order."""
    init_db()
    service.ensure_seeded()
    with session_scope() as s:
        return [
            (row.id, row.name)
            for row in s.query(TradingStrategy)
            .filter_by(status="active")
            .order_by(TradingStrategy.id)
            .all()
        ]


def run_one(strategy_id: int, *, years: int = 3) -> dict:
    """Refresh one strategy headline.

    This is the production process boundary: callers launch one process per strategy,
    so index-wide price arrays and allocator arenas cannot accumulate across the sweep.
    Pruning is deliberately separate and runs once after every strategy child exits.
    """
    init_db()
    strategy = service.get_strategy(strategy_id)["strategy"]
    start, end = _window(years)
    service.run_backtest(
        BacktestRequest(
            strategy_id=strategy_id,
            start_date=start,
            end_date=end,
            starting_cash=100000.0,
            benchmark="SPY",
            persist_headline=True,
        ),
        return_detail=False,
    )
    log.info("headline refreshed: %s", strategy["name"])
    return {
        "strategy_id": strategy_id,
        "strategy": strategy["name"],
        "window": {"start": start.isoformat(), "end": end.isoformat()},
    }


def prune_runs(*, keep_per_strategy: int = _KEEP_RUNS_PER_STRATEGY, keep_days: int = _KEEP_DAYS) -> int:
    """Delete old BacktestRun rows (children bulk-deleted first).

    Keeps the newest ``keep_per_strategy`` runs per strategy, plus anything from the
    last ``keep_days`` days regardless of count. Returns the number of runs deleted."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=keep_days)
    deleted = 0
    with session_scope() as s:
        strategy_ids = [sid for (sid,) in s.query(BacktestRun.strategy_id).distinct().all()]
        for strategy_id in strategy_ids:
            strategy_filter = (
                BacktestRun.strategy_id.is_(None)
                if strategy_id is None
                else BacktestRun.strategy_id == strategy_id
            )
            keep_ids = [rid for (rid,) in (
                s.query(BacktestRun.id)
                .filter(strategy_filter)
                .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
                .limit(max(0, keep_per_strategy))
                .all()
            )]
            while True:
                query = (
                    s.query(BacktestRun.id)
                    .filter(strategy_filter)
                    .filter(
                        (BacktestRun.created_at < cutoff)
                        | BacktestRun.created_at.is_(None)
                    )
                )
                if keep_ids:
                    query = query.filter(BacktestRun.id.notin_(keep_ids))
                chunk = [rid for (rid,) in query.order_by(BacktestRun.id.asc()).limit(500).all()]
                if not chunk:
                    break
                s.query(BacktestTrade).filter(BacktestTrade.run_id.in_(chunk)).delete(synchronize_session=False)
                s.query(BacktestEquityPoint).filter(BacktestEquityPoint.run_id.in_(chunk)).delete(synchronize_session=False)
                s.query(BacktestRun).filter(BacktestRun.id.in_(chunk)).delete(synchronize_session=False)
                deleted += len(chunk)
    if deleted:
        log.info("pruned %d old backtest runs", deleted)
    return deleted


def prune() -> int:
    """Initialize the schema and prune once after a complete headline sweep."""
    init_db()
    return prune_runs()


def run(*, years: int = 3) -> dict:
    targets = active_targets()
    start, end = _window(years)
    refreshed: list[str] = []
    failed: list[dict] = []
    for strategy_id, name in targets:
        try:
            run_one(strategy_id, years=years)
            refreshed.append(name)
        except Exception as exc:  # noqa: BLE001 — one bad model must not sink the sweep
            failed.append({"strategy": name, "error": str(exc)})
            log.warning("headline refresh failed for %s: %s", name, exc)

    result = {"window": {"start": start.isoformat(), "end": end.isoformat()},
              "strategies": len(targets), "refreshed": len(refreshed), "failed": failed,
              "pruned_runs": prune()}
    log.info("headline refresh complete: %s", {**result, "failed": len(failed)})
    return result


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    from .isolated_backtests import refresh_headlines

    print(refresh_headlines())
