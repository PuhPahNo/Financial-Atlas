"""Paper trading persistence models."""
from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..db import Base, _now


class TradingStrategy(Base):
    __tablename__ = "trading_strategies"
    __table_args__ = (UniqueConstraint("slug", name="uq_strategy_slug"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    origin = Column(String, default="seeded")
    status = Column(String, default="active")
    description = Column(String)
    history = Column(String)
    methodology = Column(String)
    parameters_json = Column(JSON, default=dict)
    defaults_json = Column(JSON, default=dict)
    metrics_json = Column(JSON, default=dict)
    caveats_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("trading_strategies.id"))
    name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    starting_cash = Column(Float)
    inputs_json = Column(JSON, default=dict)
    metrics_json = Column(JSON, default=dict)
    warnings_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)
    trades = relationship("BacktestTrade", cascade="all, delete-orphan")
    equity_points = relationship("BacktestEquityPoint", cascade="all, delete-orphan")


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False)
    trade_date = Column(Date)
    ticker = Column(String)
    side = Column(String)
    quantity = Column(Float)
    price = Column(Float)
    value = Column(Float)
    reason = Column(String)


class BacktestEquityPoint(Base):
    __tablename__ = "backtest_equity_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False)
    date = Column(Date)
    cash = Column(Float)
    equity = Column(Float)
    benchmark_equity = Column(Float)


class TraderAccount(Base):
    """A simulated 'fake trader' profile that allocates capital across strategies."""
    __tablename__ = "trader_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    emoji = Column(String, default="🦈")
    bio = Column(String, default="")
    starting_cash = Column(Float, default=100000.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    allocations = relationship("AccountAllocation", cascade="all, delete-orphan")


class AccountAllocation(Base):
    __tablename__ = "account_allocations"
    __table_args__ = (UniqueConstraint("account_id", "strategy_id", name="uq_account_strategy"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("trader_accounts.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("trading_strategies.id"), nullable=False)
    weight = Column(Float, default=0.0)  # percent (0–100) of the account's starting cash


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("trading_strategies.id"))
    name = Column(String, nullable=False)
    cash = Column(Float, default=100000.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    positions = relationship("PaperPosition", cascade="all, delete-orphan")
    orders = relationship("PaperOrder", cascade="all, delete-orphan")


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "ticker", name="uq_portfolio_ticker"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolios.id"), nullable=False)
    ticker = Column(String, nullable=False)
    quantity = Column(Float, default=0.0)
    average_cost = Column(Float, default=0.0)
    last_price = Column(Float)
    updated_at = Column(DateTime, default=_now)


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolios.id"), nullable=False)
    ticker = Column(String)
    side = Column(String)
    quantity = Column(Float)
    status = Column(String, default="open")
    reason = Column(String)
    created_at = Column(DateTime, default=_now)
    fills = relationship("PaperFill", cascade="all, delete-orphan")


class PaperFill(Base):
    __tablename__ = "paper_fills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("paper_orders.id"), nullable=False)
    filled_at = Column(DateTime, default=_now)
    price = Column(Float)
    quantity = Column(Float)
    source = Column(String)
    assumption = Column(String)
