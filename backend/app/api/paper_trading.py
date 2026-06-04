"""Paper trading API routes."""
from __future__ import annotations

from typing import Any

from datetime import date

from fastapi import APIRouter, Depends

from ..core.deps import require_paper_trading_access
from ..paper_trading import accounts, portfolio, service
from ..paper_trading.schemas import (
    AccountCreate,
    AccountRebalanceRequest,
    AccountUpdate,
    PortfolioCreate,
    PortfolioRun,
    StrategyCreate,
    StrategyUpdate,
    StrategyValidationRequest,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_paper_trading_access)])


def envelope(data: Any, *, served_by: str | None = "derived") -> dict:
    return {"data": data, "meta": {"ticker": None, "served_by": served_by, "stale": False}}


@router.get("/paper-trading/categories")
def categories():
    return envelope(service.list_categories())


@router.get("/paper-trading/strategies")
def strategies():
    return envelope(service.list_strategies())


@router.post("/paper-trading/strategies")
def create_strategy(payload: StrategyCreate):
    return envelope(service.create_strategy(payload))


@router.post("/paper-trading/strategies/validate")
def validate_strategy(payload: StrategyValidationRequest):
    return envelope(service.validate_strategy(payload))


@router.get("/paper-trading/strategies/{strategy_id}")
def get_strategy(strategy_id: int):
    return envelope(service.get_strategy(strategy_id))


@router.put("/paper-trading/strategies/{strategy_id}")
def update_strategy(strategy_id: int, payload: StrategyUpdate):
    return envelope(service.update_strategy(strategy_id, payload))


@router.post("/paper-trading/strategies/{strategy_id}/clone")
def clone_strategy(strategy_id: int):
    return envelope(service.clone_strategy(strategy_id))


@router.delete("/paper-trading/strategies/{strategy_id}")
def delete_strategy(strategy_id: int):
    return envelope(service.delete_strategy(strategy_id))


@router.post("/paper-trading/portfolios")
def create_portfolio(payload: PortfolioCreate):
    return envelope(portfolio.create_portfolio(payload))


@router.get("/paper-trading/portfolios")
def portfolios():
    return envelope(portfolio.list_portfolios())


@router.get("/paper-trading/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: int):
    return envelope(portfolio.get_portfolio(portfolio_id))


@router.post("/paper-trading/portfolios/{portfolio_id}/run")
def run_portfolio(portfolio_id: int, payload: PortfolioRun):
    return envelope(portfolio.run_portfolio(portfolio_id, payload))


# ---- Trader accounts ("fake traders") ------------------------------------

@router.post("/paper-trading/accounts")
def create_account(payload: AccountCreate):
    return envelope(accounts.create_account(payload))


@router.get("/paper-trading/accounts")
def list_accounts():
    return envelope(accounts.list_accounts())


@router.get("/paper-trading/accounts/{account_id}")
def get_account(account_id: int):
    return envelope(accounts.get_account(account_id))


@router.put("/paper-trading/accounts/{account_id}")
def update_account(account_id: int, payload: AccountUpdate):
    return envelope(accounts.update_account(account_id, payload))


@router.post("/paper-trading/accounts/{account_id}/rebalance-preview")
def rebalance_preview(account_id: int, payload: AccountRebalanceRequest):
    return envelope(accounts.rebalance_preview(account_id, payload))


@router.post("/paper-trading/accounts/{account_id}/rebalance")
def rebalance_account(account_id: int, payload: AccountRebalanceRequest):
    return envelope(accounts.rebalance_account(account_id, payload))


@router.delete("/paper-trading/accounts/{account_id}")
def delete_account(account_id: int):
    return envelope(accounts.delete_account(account_id))


@router.get("/paper-trading/accounts/{account_id}/performance")
def account_performance(account_id: int, start: date | None = None, end: date | None = None):
    return envelope(accounts.account_performance(account_id, start, end))


@router.get("/paper-trading/accounts/{account_id}/value")
def account_value(account_id: int):
    """Lightweight live-ish mark for polling — marks settled holdings to a fresh quote
    while the market is open, else returns the EOD baseline. Cheap relative to /performance."""
    return envelope(accounts.ensure_fresh_mark(account_id))
