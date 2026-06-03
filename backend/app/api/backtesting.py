"""Backtesting API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..paper_trading import service
from ..paper_trading.schemas import BacktestRequest

router = APIRouter(prefix="/api/v1")


def envelope(data: Any, *, served_by: str | None = "derived") -> dict:
    return {"data": data, "meta": {"ticker": None, "served_by": served_by, "stale": False}}


@router.post("/backtests")
def run_backtest(payload: BacktestRequest):
    result = service.run_backtest(payload)
    return envelope(result, served_by=result.get("served_by", "derived"))


@router.get("/backtests/{run_id}")
def get_backtest(run_id: int):
    return envelope(service.get_backtest(run_id))
