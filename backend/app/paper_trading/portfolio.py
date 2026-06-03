"""Simulated paper-portfolio accounting."""
from __future__ import annotations

from ..core.errors import NotFoundError, ValidationError
from ..db import session_scope
from ..models.paper_trading import PaperFill, PaperOrder, PaperPortfolio, PaperPosition, TradingStrategy
from .schemas import PortfolioCreate, PortfolioRun, normalize_tickers


def create_portfolio(payload: PortfolioCreate) -> dict:
    with session_scope() as session:
        strategy = session.get(TradingStrategy, payload.strategy_id)
        if not strategy or strategy.status != "active":
            raise NotFoundError(f"Strategy {payload.strategy_id} not found")
        portfolio = PaperPortfolio(strategy_id=payload.strategy_id, name=payload.name.strip(), cash=payload.starting_cash)
        session.add(portfolio)
        session.flush()
        return {"portfolio": _portfolio_view(portfolio)}


def list_portfolios() -> dict:
    with session_scope() as session:
        portfolios = session.query(PaperPortfolio).order_by(PaperPortfolio.created_at.desc()).all()
        return {"portfolios": [_portfolio_view(row) for row in portfolios]}


def get_portfolio(portfolio_id: int) -> dict:
    with session_scope() as session:
        portfolio = session.get(PaperPortfolio, portfolio_id)
        if not portfolio:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return {"portfolio": _portfolio_view(portfolio)}


def run_portfolio(portfolio_id: int, payload: PortfolioRun) -> dict:
    with session_scope() as session:
        portfolio = session.get(PaperPortfolio, portfolio_id)
        if not portfolio:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        strategy = session.get(TradingStrategy, portfolio.strategy_id)
        if not strategy:
            raise NotFoundError(f"Strategy {portfolio.strategy_id} not found")
        params = strategy.parameters_json or {}
        tickers = normalize_tickers(params.get("tickers", []))
        if not tickers:
            raise ValidationError("Strategy needs at least one ticker to run")
        price, source = _latest_price(tickers[0], payload.use_fixture_data)
        allocation = max(0.01, min(float(params.get("allocation_pct", 0.25)), 1.0))
        quantity = int((portfolio.cash * allocation) / price)
        if quantity <= 0:
            raise ValidationError("Portfolio cash is too low for a simulated fill")

        order = PaperOrder(
            portfolio_id=portfolio.id,
            ticker=tickers[0],
            side="buy",
            quantity=quantity,
            status="filled",
            reason="strategy allocation run",
        )
        session.add(order)
        session.flush()
        session.add(PaperFill(
            order_id=order.id,
            price=price,
            quantity=quantity,
            source=source,
            assumption="market-on-close simulated fill",
        ))
        _apply_position(session, portfolio, tickers[0], quantity, price)
        portfolio.cash -= quantity * price
        session.flush()
        return {"portfolio": _portfolio_view(portfolio)}


def _apply_position(session, portfolio: PaperPortfolio, ticker: str, quantity: int, price: float) -> None:
    position = session.query(PaperPosition).filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
    total_cost = quantity * price
    if position:
        old_value = position.quantity * position.average_cost
        position.quantity += quantity
        position.average_cost = (old_value + total_cost) / position.quantity
        position.last_price = price
        return
    session.add(PaperPosition(portfolio_id=portfolio.id, ticker=ticker, quantity=quantity, average_cost=price, last_price=price))


def _portfolio_view(portfolio: PaperPortfolio) -> dict:
    return {
        "id": portfolio.id,
        "strategy_id": portfolio.strategy_id,
        "name": portfolio.name,
        "cash": portfolio.cash,
        "status": portfolio.status,
        "positions": [{
            "ticker": position.ticker,
            "quantity": position.quantity,
            "average_cost": position.average_cost,
            "last_price": position.last_price,
        } for position in portfolio.positions],
        "orders": [{
            "id": order.id,
            "ticker": order.ticker,
            "side": order.side,
            "quantity": order.quantity,
            "status": order.status,
            "fills": [{
                "price": fill.price,
                "quantity": fill.quantity,
                "source": fill.source,
                "assumption": fill.assumption,
            } for fill in order.fills],
        } for order in portfolio.orders],
    }


def _latest_price(ticker: str, use_fixture_data: bool) -> tuple[float, str]:
    if use_fixture_data:
        return 13.0, "fixture"
    from ..services import prices

    payload, served_by = prices.price_history(ticker, range="1m", interval="1d")
    bars = payload.get("bars") or []
    if not bars:
        raise ValidationError("No price bars available for simulated portfolio run", ticker=ticker)
    return float(bars[-1]["close"]), served_by
