# BI-2 — Screening backtest engine

Status: implemented

## Scope

- `backend/app/backtesting/screen.py`: `run_screen_backtest(strategy, tickers, start, end,
  starting_cash, cost_rate, benchmark, eligible_fn)`.
  - Prefetch daily bars per candidate over `[start − warmup, end]` (+ benchmark).
  - Trading calendar = union of in-window bar dates; rebalance on the window start and the
    first trading day of each month.
  - At each rebalance: evaluate `eligible_fn` per candidate (point-in-time), select passers,
    rank by score, cap at `max_positions`, equal-weight (shorts negative, capped).
  - Trade to targets; apply `cost_rate` on turnover; mark daily → equity curve with
    `benchmark_equity`.
  - Produce `final_holdings` (pre-final-mark settled positions) + `residual_cash`.
- Returns the same dict contract as `run_backtest`.

## Acceptance

- Nothing eligible across the window → equity flat at `starting_cash`, no trades.
- A name becomes eligible mid-window → first buy trade dated at/after that rebalance, never
  day 1.
- Equity curve spans the window; metrics computed via existing `summarize`.

## Test

- Covered in `backend/tests/test_screen_backtest.py` (BI-5) via synthetic bars + stub eligible.
