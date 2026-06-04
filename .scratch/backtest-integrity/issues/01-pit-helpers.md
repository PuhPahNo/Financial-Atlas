# BI-1 — Point-in-time factor + fundamentals helpers

Status: implemented

## Scope

- `backend/app/backtesting/factors.py`: pure functions over a date-sorted bar list, each
  using only bars with `date <= D`: `sma(bars, D, n)`, `momentum(bars, D, lookback)`,
  `trend(bars, D, n)` (close/SMA − 1), `relative_strength(bars, bench, D, lookback)`,
  `volatility(bars, D, lookback)`, `new_high(bars, D, channel)`, `close_on(bars, D)`,
  `pct_change(bars, D, window)`. Return None when history is insufficient.
- `backend/app/backtesting/pit_fundamentals.py`: `as_of(ticker, D)` → most recent annual
  fundamentals with `filing_date <= D` from the EDGAR provider, with derived metrics
  (`fcf`, `fcf_margin`, `fcf_conversion`, `net_debt`, `net_debt_to_fcf`, `dividends_paid`,
  `shares`). Returns None if nothing filed by D. Cached companyfacts → in-memory filter.

## Acceptance

- A price spike at D+5 does not change `momentum`/`sma`/`new_high` at D.
- `as_of(ticker, D)` ignores filings dated after D; picks the latest filed ≤ D.
- Missing/partial data → None, never raises.

## Test

- `backend/tests/test_pit_factors.py` with synthetic bars + stubbed statements.
