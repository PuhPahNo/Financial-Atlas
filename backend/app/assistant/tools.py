"""Assistant tool registry."""
from __future__ import annotations

from datetime import date

from ..core.errors import NotFoundError
from ..paper_trading.schemas import StrategyCreate
from ..paper_trading import accounts as account_service
from ..paper_trading import portfolio as portfolio_service
from ..paper_trading import service as paper_service
from ..services import company, financials, prices
from ..valuation import service as valuation_service
from ..providers.base import Period

def _tokens(value: str) -> set[str]:
    return {part for part in value.lower().replace("&", " ").split() if len(part) > 1}


def _best_dict_match(rows: list[dict], name: str) -> dict | None:
    needle = " ".join(str(name or "").strip().lower().split())
    if not needle:
        return None
    for row in rows:
        if " ".join(str(row.get("name", "")).lower().split()) == needle:
            return row
    wanted = _tokens(needle)
    best, best_score = None, 0
    for row in rows:
        score = len(wanted & _tokens(str(row.get("name", ""))))
        if score > best_score:
            best, best_score = row, score
    return best if best_score else None


def _strategy_id(payload: dict) -> int:
    if payload.get("strategy_id"):
        return int(payload["strategy_id"])
    match = _best_dict_match(paper_service.list_strategies().get("strategies", []), str(payload.get("strategy_name", "")))
    if not match:
        raise NotFoundError(f"Strategy '{payload.get('strategy_name', '')}' not found")
    return int(match["id"])


def _account_id(payload: dict) -> int:
    if payload.get("account_id"):
        return int(payload["account_id"])
    match = _best_dict_match(account_service.list_accounts().get("accounts", []), str(payload.get("account_name", "")))
    if not match:
        raise NotFoundError(f"Trader account '{payload.get('account_name', '')}' not found")
    return int(match["id"])


def _date_arg(payload: dict, key: str) -> date | None:
    value = payload.get(key)
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _allocations(payload: dict) -> list[dict]:
    rows = []
    for item in payload.get("allocations", []):
        row = dict(item)
        if not row.get("strategy_id") and row.get("strategy_name"):
            row["strategy_id"] = _strategy_id({"strategy_name": row["strategy_name"]})
        rows.append({"strategy_id": int(row["strategy_id"]), "weight": float(row.get("weight", 0))})
    return rows


def execute_read_tool(action: str, payload: dict) -> dict:
    ticker = str(payload.get("ticker", "")).upper()
    if action == "get_company_overview":
        return company.overview(ticker)
    if action == "get_cash_flow_analysis":
        result = financials.cash_flow_analysis(ticker, Period.ANNUAL)
        return {"periods": result["periods"], "served_by": result["served_by"]}
    if action == "get_valuation":
        return valuation_service.valuate(ticker)
    if action == "get_price_history":
        data, served_by = prices.price_history(ticker, range=payload.get("range", "1y"), interval="1d")
        return {"served_by": served_by, **data}
    if action == "list_strategies":
        return paper_service.list_strategies()
    if action == "list_accounts":
        return account_service.list_accounts()
    if action == "get_account":
        return account_service.get_account(_account_id(payload))
    if action == "account_performance":
        account_id = _account_id(payload)
        result = account_service.account_performance(
            account_id,
            start=_date_arg(payload, "start_date"),
            end=_date_arg(payload, "end_date"),
        )
        result["account"] = account_service.get_account(account_id)["account"]
        return result
    if action == "rebalance_preview":
        from ..paper_trading.schemas import AccountRebalanceRequest

        return account_service.rebalance_preview(
            _account_id(payload),
            AccountRebalanceRequest(allocations=_allocations(payload)),
        )
    if action == "validate_strategy":
        from ..paper_trading.schemas import StrategyValidationRequest

        return paper_service.validate_strategy(StrategyValidationRequest(**payload))
    if action == "run_backtest":
        from ..paper_trading.schemas import BacktestRequest

        return paper_service.run_backtest(BacktestRequest(**payload))
    raise ValueError(f"Unknown read tool: {action}")


def execute_write_tool(action: str, payload: dict) -> dict:
    if action == "create_strategy":
        return paper_service.create_strategy(StrategyCreate(**payload))
    if action == "update_strategy":
        from ..paper_trading.schemas import StrategyUpdate

        strategy_id = _strategy_id(payload)
        payload.pop("strategy_id", None)
        return paper_service.update_strategy(strategy_id, StrategyUpdate(**payload))
    if action == "delete_strategy":
        return paper_service.delete_strategy(_strategy_id(payload))
    if action == "clone_strategy":
        return paper_service.clone_strategy(_strategy_id(payload))
    if action == "create_portfolio":
        from ..paper_trading.schemas import PortfolioCreate

        return portfolio_service.create_portfolio(PortfolioCreate(**payload))
    if action == "assign_strategy_to_account":
        return account_service.assign_strategy_to_account(
            account_name=str(payload.get("account_name", "")),
            strategy_name=str(payload.get("strategy_name", "")),
            weight=float(payload.get("weight", 0)),
        )
    if action == "rebalance_account":
        from ..paper_trading.schemas import AccountRebalanceRequest

        return account_service.rebalance_account(
            _account_id(payload),
            AccountRebalanceRequest(allocations=_allocations(payload)),
        )
    raise ValueError(f"Unknown write tool: {action}")
