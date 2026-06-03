# Model Versioning And Parameter Sweeps

Status: implemented

## Problem

Model edits overwrite current strategy state, making it hard to compare iterations or tune parameters
scientifically.

## Scope

- Add model versions or immutable backtest snapshots.
- Add parameter sweep runs for selected numeric parameters.
- Compare return, Sharpe, drawdown, turnover, win rate, and exposure.

## Acceptance Criteria

- Backtest results retain the exact config used at run time.
- Sweeps produce a ranked table and preserve each tested parameter set.
- Existing single-run backtests still work.

## Implementation Notes

- Single backtest runs now store an immutable `strategy_snapshot` inside `inputs_json`.
- Added `/api/v1/backtests/sweep` for ranked numeric-parameter sweeps.
- Sweep variants persist as ordinary backtest runs with `inputs.sweep` and exact tested
  `strategy_snapshot` metadata.
- Sweep comparison metrics include return, Sharpe, max drawdown, win rate, turnover, and exposure.
- Backtest Lab now discovers numeric parameters and renders a sweep control plus ranked table.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_paper_trading_api.py backend/tests/test_strategy_validation.py`
  -> 12 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 46 passed.
- `npm run build` in `frontend/` -> passed.
- Browser smoke on `http://localhost:3000/paper-trading` verified Backtest Lab shows an enabled
  Parameter sweep panel for seeded models and no stale test strategy rows.
