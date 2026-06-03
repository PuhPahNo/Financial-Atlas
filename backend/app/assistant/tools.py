"""Assistant tool registry."""
from __future__ import annotations

from ..paper_trading.schemas import StrategyCreate
from ..paper_trading import accounts as account_service
from ..paper_trading import portfolio as portfolio_service
from ..paper_trading import service as paper_service
from ..services import company, financials, prices
from ..valuation import service as valuation_service
from ..providers.base import Period

READ_ONLY_TOOLS = {
    "get_company_overview",
    "get_cash_flow_analysis",
    "get_valuation",
    "get_price_history",
    "list_strategies",
    "run_backtest",
}

WRITE_TOOLS = {"create_strategy", "update_strategy", "delete_strategy", "create_portfolio", "assign_strategy_to_account"}


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
    if action == "run_backtest":
        from ..paper_trading.schemas import BacktestRequest

        return paper_service.run_backtest(BacktestRequest(**payload))
    raise ValueError(f"Unknown read tool: {action}")


def execute_write_tool(action: str, payload: dict) -> dict:
    if action == "create_strategy":
        return paper_service.create_strategy(StrategyCreate(**payload))
    if action == "update_strategy":
        from ..paper_trading.schemas import StrategyUpdate

        strategy_id = int(payload.pop("strategy_id"))
        return paper_service.update_strategy(strategy_id, StrategyUpdate(**payload))
    if action == "delete_strategy":
        return paper_service.delete_strategy(int(payload["strategy_id"]))
    if action == "create_portfolio":
        from ..paper_trading.schemas import PortfolioCreate

        return portfolio_service.create_portfolio(PortfolioCreate(**payload))
    if action == "assign_strategy_to_account":
        return account_service.assign_strategy_to_account(
            account_name=str(payload.get("account_name", "")),
            strategy_name=str(payload.get("strategy_name", "")),
            weight=float(payload.get("weight", 0)),
        )
    raise ValueError(f"Unknown write tool: {action}")
