# Phase 03 — Account live mark + value endpoint

Status: implemented

## Problem

Accounts have no stateful holdings to mark and no cheap endpoint to poll for a live value.

## Scope

- `backend/app/paper_trading/accounts.py`:
  - `account_holdings(account_id)` — run each sleeve's backtest once, aggregate
    `final_holdings` into net long quantities per ticker, short positions
    (`ticker, qty, entry_price`), and total baseline `cash` (account uninvested cash +
    each sleeve's `residual_cash`); record `eod_value` and `as_of_date`. Cache with a
    daily-ish TTL keyed by `(account_id, allocation-signature, last_trading_day)`.
  - `ensure_fresh_mark(account_id)` — load/refresh the holdings snapshot, then if market
    open and mark stale, fetch live quotes and compute `previous_close_value`,
    `live_value`, `day_change`, `day_change_pct`. Market closed → EOD baseline,
    `market_open=false`. Quote failure → EOD baseline, `stale=true`. Returns the value dict.
- `backend/app/api/paper_trading.py`: `GET /paper-trading/accounts/{id}/value` →
  `envelope(accounts.ensure_fresh_mark(id))`. Payload: `current_value`, `eod_value`,
  `day_change`, `day_change_pct`, `as_of`, `market_open`, `delayed_minutes=15`,
  `served_by`, `stale`.

## Acceptance Criteria

- Long-only account: `current_value == cash + Σ qty*price`; reconciles.
- Short sleeve: marked via `entry_price − price`.
- Market closed → `market_open=false`, value == `eod_value`.
- Raising quote fn → `stale=true`, value == `eod_value`.
- `/performance` endpoint and its tests unchanged.

## Test

- Extend `backend/tests/test_paper_trading_api.py`: monkeypatch holdings + quotes
  (mirroring the `execute_backtest` monkeypatch pattern).
