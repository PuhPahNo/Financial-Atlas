"""Pydantic contracts for paper trading APIs."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Category = Literal[
    "long_term",
    "short_term",
    "short_selling",
    "options",
    "income_quality",
    "risk_rotation",
]


class StrategyCreate(BaseModel):
    category: Category
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=800)
    history: str = Field(default="", max_length=1200)
    methodology: str = Field(default="", max_length=1600)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    category: Category | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=800)
    history: str | None = Field(default=None, max_length=1200)
    methodology: str | None = Field(default=None, max_length=1600)
    parameters: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    caveats: list[str] | None = None


class StrategyValidationRequest(BaseModel):
    category: Category
    parameters: dict[str, Any] = Field(default_factory=dict)


class _BacktestWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    starting_cash: float = Field(default=100000.0, gt=0)
    benchmark: str = "SPY"
    transaction_cost_bps: float = Field(default=5.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)


class BacktestRequest(_BacktestWindow):
    strategy_id: int | None = None
    strategy: StrategyCreate | None = None
    tickers: list[str] = Field(default_factory=list)
    persist_headline: bool = False  # store a compact equity preview on the strategy
    # queue=True enqueues the run and returns immediately with status="queued";
    # poll GET /backtests/{id}. Long runs otherwise die at proxy timeouts
    # (Next dev proxy ~30s, Render edge ~100s) while the engine keeps grinding.
    queue: bool = False
    assistant_context: dict[str, Any] = Field(default_factory=dict)


class ParameterSweepRequest(_BacktestWindow):
    strategy_id: int
    parameter: str = Field(min_length=1, max_length=120)
    values: list[float] = Field(min_length=1, max_length=12)
    rank_by: Literal["total_return", "sharpe", "max_drawdown", "win_rate", "turnover", "exposure"] = "total_return"


class AllocationInput(BaseModel):
    strategy_id: int
    weight: float = Field(ge=0, le=100)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    emoji: str = Field(default="🦈", max_length=8)
    bio: str = Field(default="", max_length=300)
    starting_cash: float = Field(default=100000.0, gt=0)
    allocations: list[AllocationInput] = Field(default_factory=list)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    emoji: str | None = Field(default=None, max_length=8)
    bio: str | None = Field(default=None, max_length=300)
    starting_cash: float | None = Field(default=None, gt=0)
    allocations: list[AllocationInput] | None = None


class AccountRebalanceRequest(BaseModel):
    allocations: list[AllocationInput] = Field(default_factory=list)


def normalize_tickers(tickers: list[str]) -> list[str]:
    return [ticker.strip().upper() for ticker in tickers if ticker.strip()]
