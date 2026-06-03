# Strategy Rule Validation

Status: implemented

## Problem

Paper Trading supports rule-based strategies, but model configs need stronger validation and clearer
editing affordances before more strategy types are added.

## Scope

- Define a typed rule schema for long, short, risk-rotation, income, and synthetic options-themed
  strategy families.
- Validate required fields, ranges, and incompatible combinations.
- Improve model configuration page state for invalid, saved, and backtested configs.

## Acceptance Criteria

- Invalid rules fail before backtest execution.
- Config UI shows exact missing or invalid inputs.
- Tests cover at least one valid and invalid rule per family.

## Implementation Notes

- Added `backend/app/paper_trading/validation.py` as the typed validation boundary for rule
  strategies.
- Strategy create/update and backtest execution now call validation before persistence or engine
  execution.
- Added `/api/v1/paper-trading/strategies/validate` for UI and Copilot preflight checks.
- Rule Builder now shows field-level validation messages and includes synthetic-options assumption
  metadata for options-family rules.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_strategy_validation.py backend/tests/test_paper_trading_api.py`
  -> 10 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 44 passed.
- `npm run build` in `frontend/` -> passed.
- Browser smoke on `http://localhost:3000/paper-trading` verified Build -> Signal rule mode shows:
  - missing model name error.
  - Short Selling family with long direction error.
