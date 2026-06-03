# Risk Dashboard And Attribution

Status: implemented

## Problem

Profiles need more than headline return; users need drawdown, exposure, concentration, and strategy
contribution to understand model behavior.

## Scope

- Add profile risk metrics and attribution by strategy.
- Show drawdown curve, exposure, concentration, turnover, and top contributors.
- Keep seeded illustrative metrics visually separate from user backtests.

## Acceptance Criteria

- Account performance endpoint returns attribution sections.
- UI distinguishes simulated, seeded, and user-backtested metrics.
- Tests verify attribution sums reconcile to account-level performance.

## Implementation Notes

- Account performance now returns `risk`, `attribution`, and `drawdown_curve` sections.
- Risk metrics include gross exposure, cash percentage, concentration, Herfindahl index, turnover,
  and max drawdown.
- Attribution includes top contributors, laggards, allocation rows, and reconciliation of strategy
  ending values plus cash back to account current value.
- Trader Detail now renders a Risk dashboard with exposure, concentration, turnover, HHI,
  contribution reconciliation, and drawdown chart data.
- Existing model surfaces continue to label illustrative/seeded versus backtested states, and
  archived strategy context carries through account attribution.

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests/test_paper_trading_api.py` -> 12 passed.
- `PYTHONPATH=backend pytest backend/tests` -> 49 passed.
- `npm run build` in `frontend/` -> passed.
- Browser smoke on `http://localhost:3000/paper-trading` created a temporary QA trader, opened
  Trader Detail, verified the Risk dashboard shows Exposure, Concentration, Turnover, and Strategy
  contributions, then deleted the temporary trader.
