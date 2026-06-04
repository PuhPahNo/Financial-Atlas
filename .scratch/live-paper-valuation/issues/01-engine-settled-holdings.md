# Phase 01 — Backtest engine exposes settled holdings

Status: implemented

## Problem

The live overlay must mark the shares a strategy holds going into the next session.
The engine liquidates on the last bar, so the final equity point is post-sale cash and
cannot be re-marked. We need the pre-liquidation position, additively.

## Scope

- In `backend/app/backtesting/engine.py`, capture the settled position in both `_buy_hold`
  and `_run_rules` **before** the synthetic end-of-window sale.
- Return a new `final_holdings` list from `run_backtest`: per instrument
  `{ticker, quantity, direction, entry_price, last_close}` plus a `residual_cash` float.
- Long buy-and-hold: one long holding of `quantity` shares at `last_close`, `entry_price`
  = buy price, `residual_cash` = pre-sale cash.
- Rule-based: the open position at window end if any (`direction`, `entry_price`, `qty`),
  else no holdings; `residual_cash` = pre-liquidation cash. Flat → empty holdings, all cash.
- Do NOT change `equity_curve`, `metrics`, `trades`, or the weight-based `holdings`.

## Acceptance Criteria

- A fixture buy-and-hold run returns `final_holdings` with one long position, positive
  quantity, and `last_close` == the last fixture close (13.0).
- `residual_cash + quantity*last_close` ≈ pre-liquidation equity.
- All existing backtest/paper-trading tests still pass unchanged.

## Test

- `PYTHONPATH=backend pytest backend/tests/test_paper_trading_api.py` green.
- New assertions on `final_holdings` via the backtests API or a direct engine call.
