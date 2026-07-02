"""Backtesting API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..core.deps import require_paper_trading_access
from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest, ParameterSweepRequest

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_paper_trading_access)])


def envelope(data: Any, *, served_by: str | None = "derived") -> dict:
    return {"data": data, "meta": {"ticker": None, "served_by": served_by, "stale": False}}


@router.post("/backtests")
def run_backtest(payload: BacktestRequest):
    """Run a backtest. With queue=true the run is enqueued for the in-process worker
    and returned immediately with status="queued" — poll GET /backtests/{id}. The
    synchronous form stays for scripts/tests but dies at proxy timeouts on long runs."""
    if payload.queue:
        return envelope(service.enqueue_backtest(payload))
    result = service.run_backtest(payload)
    return envelope(result, served_by=result.get("served_by", "derived"))


@router.post("/backtests/sweep")
def run_parameter_sweep(payload: ParameterSweepRequest):
    return envelope(service.run_parameter_sweep(payload))


@router.get("/backtests")
def list_backtests(strategy_id: int | None = None, limit: int = 20):
    """Recent runs (optionally for one strategy) — id, status, window, headline metrics."""
    return envelope(service.list_backtests(strategy_id=strategy_id, limit=limit))


@router.get("/backtests/{run_id}")
def get_backtest(run_id: int):
    return envelope(service.get_backtest(run_id))


@router.post("/backtests/{run_id}/cancel")
def cancel_backtest(run_id: int):
    """Cancel a queued run. Running jobs finish; their status is returned unchanged."""
    return envelope(service.cancel_backtest(run_id))


@router.post("/backtests/warm")
def warm_backtest_data(years: int = 25, include_fundamentals: bool = True):
    """Pre-fill the durable price store + PIT fundamentals for the investable superset
    so subsequent backtests run from local data (best-effort, long-running)."""
    from ..jobs import warm_prices
    return envelope(warm_prices.run(years=years, include_fundamentals=include_fundamentals))


@router.post("/backtests/refresh-headlines")
def refresh_headlines(years: int = 3):
    """Re-run every active strategy's headline backtest with the current engine and
    persist it onto the card (best-effort, long-running). Run after /backtests/warm."""
    from ..jobs import refresh_headlines as job
    return envelope(job.run(years=years))
