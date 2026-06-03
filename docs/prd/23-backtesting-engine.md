# 23 — Backtesting Engine

> Parent: [00-master-prd.md](00-master-prd.md) · Deterministic EOD strategy simulation.

## 1. Purpose / why

Let users test a trading strategy against historical market data before trusting it in a simulated
portfolio. The engine emphasizes reproducibility, visible assumptions, and honest free-data limits.

## 2. User stories & acceptance criteria

- *As a user,* I can backtest any saved or inline strategy over a date range. **AC:** request accepts
  strategy, ticker universe, benchmark, dates, starting cash, slippage, and transaction costs.
- *As an analyst,* I can see whether a strategy survived a crisis period. **AC:** results include
  trades, holdings, cash, equity curve, drawdown, benchmark comparison, and summary metrics.
- *As a maintainer,* I can reproduce a run. **AC:** run inputs, parameter values, data source, and
  warnings are persisted.

## 3. Scope (in / out)

- **In:** daily OHLCV bars, deterministic signal evaluation, market-on-close fills, transaction-cost
  assumptions, benchmark comparison, result persistence, and warnings.
- **Out:** live execution, tick-level fills, level-2 data, margin interest, tax lots, and real
  options-chain pricing until a free historical source exists.

## 4. Backtest contract

Inputs:
- strategy id or inline strategy spec
- tickers or universe definition
- start/end dates
- starting cash
- position sizing and rebalance frequency
- transaction cost, slippage, benchmark, and risk limits

Outputs:
- trades, fills, holdings, cash, equity curve, drawdown curve
- CAGR, total return, max drawdown, volatility, Sharpe-like ratio, win rate, turnover
- benchmark return and excess return
- warnings for missing data, unsupported assumptions, and synthetic options behavior

## 5. Strategy interface

Strategies expose metadata, validated parameters, and a signal function that receives only normalized
historical observations. The engine owns accounting and fills, so strategy code cannot mutate cash or
positions directly.

## 6. Edge cases

- Empty or invalid date ranges fail fast with `INVALID_REQUEST`.
- Missing bars skip the affected day and append a warning.
- Delisted-symbol survivorship bias is disclosed because free data may not cover it.
- `discount_rate`, valuation inputs, and fundamentals-driven filters use Atlas services, not duplicate
  calculations.

## 7. Testing requirements

- Unit tests use tiny fixture price series with hand-computed expected trades and equity.
- Metrics tests verify total return, CAGR, drawdown, win rate, and benchmark comparison.
- API tests validate request ranges and response envelope shape.

## 8. Done criteria

A user can run a 2006-2009 backtest for a strategy, inspect the trades the strategy would have made,
see account balance over time, compare to a benchmark, and understand any data limitations.
