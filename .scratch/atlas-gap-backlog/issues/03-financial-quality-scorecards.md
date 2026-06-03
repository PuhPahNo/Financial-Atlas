# Financial Quality Scorecards

Status: implemented

Progress: implemented

## Problem

Cash flow and fundamentals expose useful metrics, but users still have to synthesize quality,
capital allocation, and risk manually.

## Scope

- Add derived quality buckets for cash conversion, reinvestment, capital returns, balance sheet, and
  growth durability.
- Explain formulas and data limitations.
- Keep calculations pure and testable.

## Acceptance Criteria

- Scorecards derive from existing statement and cash-flow-analysis data.
- Missing or invalid inputs produce `null` plus reason strings, never misleading zeroes.
- Unit tests cover formula and denominator edge cases.

## Implementation Notes

- Added `cash_flow_scorecard` in `backend/app/services/financials.py`.
- Cash-flow analysis now returns a reusable `scorecard` with overall score, per-card score, tone,
  summary, and drivers.
- Scorecard cards cover cash conversion, capital allocation, reinvestment load, SBC load, balance
  sheet pressure, and FCF growth.
- Cash-flow analysis now joins balance-sheet data when available to compute `net_debt` and
  `net_debt_to_fcf`; balance-sheet lookup failure does not break the cash-flow endpoint.
- Cash Flow UI now renders a compact quality scorecard above the allocation and FCF charts.

## QA Evidence

- `backend/.venv/bin/python -m pytest tests/test_financial_quality.py tests/test_company_snapshot_api.py -q`
  from `backend/`: 6 passed.
- `backend/.venv/bin/python -m pytest -q` from `backend/`: 29 passed.
- `npm run build` from `frontend/`: passed.
- Browser smoke at `http://localhost:3000/company/AAPL/cash-flow`: scorecard rendered cash
  conversion, capital allocation, reinvestment, SBC, balance sheet, and FCF growth with no error page.
