# Full Regression QA Suite

Status: implemented

## Problem

The current manual QA path is broad and valuable, but it should become repeatable so future changes
do not regress the financial tabs, Paper Trading, or Copilot workflows.

## Scope

- Add backend API tests for financial snapshot, paper-trading CRUD/backtest/account flows, and
  assistant confirmed actions.
- Add browser smoke checks for company tabs and Paper Trading views.
- Add cleanup fixtures for generated strategies, accounts, sessions, and runs.

## Acceptance Criteria

- Tests cover creating, saving, backtesting, assigning, and deleting/archiving a test strategy.
- Browser smoke covers overview, cash flow, valuation, Paper Trading builder, backtest, trader
  profile, and Copilot panel.
- QA records are cleaned up after tests.

## Implementation Notes

- Added a full paper-trading API regression test for create -> save/update -> fixture backtest -> assign to trader -> archive strategy -> verify archived account context -> delete trader.
- Extended cleanup fixtures for generated full-QA strategies, accounts, assistant sessions, and runs.
- Added `.scratch/atlas-gap-backlog/final-gap-report.md` with completed coverage, QA evidence, browser smoke results, and remaining caveats.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_paper_trading_api.py` -> 13 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 58 passed.
- `npm run build` -> passed.
- Browser smoke on `http://127.0.0.1:3000`:
  - `/company/AAPL`
  - `/company/AAPL/cash-flow`
  - `/company/AAPL/valuation`
  - `/screener`
  - `/paper-trading`
  - Paper Trading tabs: Build, Backtest, Traders, Copilot
  - Copilot pending/rejected action-status flow

Screenshot capture through the browser bridge timed out twice; DOM/browser smoke and automated tests are the recorded evidence.
