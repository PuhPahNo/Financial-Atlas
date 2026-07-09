"""Paper trading API routes."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from ..core.deps import require_paper_trading_access
from ..paper_trading import accounts, service
from ..paper_trading.schemas import (
    AccountCreate,
    AccountRebalanceRequest,
    AccountUpdate,
    StrategyCreate,
    StrategyUpdate,
    StrategyValidationRequest,
)
from .responses import derived_envelope as envelope

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_paper_trading_access)])

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


@router.get("/paper-trading/strategies-archived")
def list_archived_strategies():
    return envelope(service.list_archived_strategies())


@router.post("/paper-trading/strategies/{strategy_id}/unarchive")
def unarchive_strategy(strategy_id: int):
    return envelope(service.unarchive_strategy(strategy_id))


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
