# Valuation Diagnostics And History

Status: implemented

Progress: implemented

## Problem

The valuation page computes model outputs, but users need better visibility into applicability,
assumption sensitivity, and historical recomputation.

## Scope

- Show model applicability reasons and reweighted blend math.
- Add sensitivity grids for discount rate, growth, terminal growth, and key multiples.
- Persist or retrieve valuation history where the backend already supports it.

## Acceptance Criteria

- Unusable models show explicit reasons.
- Sensitivity outputs use the same valuation service path as the main result.
- Tests cover monotonicity and impossible assumptions.

## Implementation Notes

- Added valuation diagnostics to `backend/app/valuation/service.py`.
- Diagnostics expose per-model applicability, exclusion reason, requested weight, applied weight,
  contribution, and blend renormalization.
- Added service-computed sensitivity grids for discount rate x FCF growth, discount rate x terminal
  growth, and key multiple stress.
- Added `valuation_results` persistence and `GET /api/v1/valuation/{ticker}/history`.
- Valuation GET/POST routes record explicit valuation-page calls; overview snapshots remain read-only.
- Added duplicate protection so repeated refreshes with identical assumptions do not spam history.
- Updated the valuation page to render diagnostics, backend sensitivity grids, and recent history.

## QA Evidence

- `backend/.venv/bin/python -m pytest tests/test_valuation.py tests/test_valuation_api.py -q`
  from `backend/`: 13 passed.
- `backend/.venv/bin/python -m pytest -q` from `backend/`: 32 passed.
- `npm run build` from `frontend/`: passed.
- Direct live endpoint check: `GET /api/v1/valuation/AAPL` returned diagnostics with six model rows
  and sensitivity grids for discount/growth, discount/terminal, and multiples.
- Direct live endpoint check: `GET /api/v1/valuation/AAPL/history?limit=3` returned persisted history
  rows after a valuation call.
- Browser smoke at `http://localhost:3000/company/AAPL/valuation`: diagnostics, sensitivity grids,
  and history rendered with no error page.
- Cleaned the AAPL smoke-test history rows after verification.
