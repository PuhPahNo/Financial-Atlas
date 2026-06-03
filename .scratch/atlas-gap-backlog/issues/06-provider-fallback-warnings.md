# Provider Fallback Warnings

Status: implemented

Progress: implemented

## Problem

When optional providers are unavailable or partial, the UI often lacks enough context for users to
trust what is missing versus broken.

## Scope

- Normalize per-section warnings for unavailable keys, provider errors, and missing data.
- Add UI surfaces for partial data without overloading the main analysis.
- Keep provider secrets and diagnostics server-side.

## Acceptance Criteria

- API responses include concise warning objects.
- UI labels unavailable analyst/news/peer data as unavailable rather than failed analysis.
- Provider exception details are logged, not shown directly to users.

## Implementation Notes

- Added normalized warning helpers in `backend/app/services/research.py`.
- News, analyst, and peers responses now include concise warnings for disabled optional providers,
  provider errors, and no-data states.
- Provider exceptions are logged with server-side details; API warning messages do not expose raw
  exception text, keys, or provider payloads.
- Research routes now promote warnings into `meta.warnings` while also keeping warnings in the
  response body for local section UI.
- Company snapshot aggregation now promotes research warnings into top-level snapshot warnings and
  per-section `sections.*.warnings`.
- Overview UI now surfaces provider notes as a small provider-note block instead of treating all
  optional-data gaps as hard failures.

## QA Evidence

- `backend/.venv/bin/python -m pytest tests/test_research_warnings.py tests/test_company_snapshot_api.py -q`
  from `backend/`: 8 passed.
- `backend/.venv/bin/python -m pytest -q` from `backend/`: 41 passed.
- `npm run build` from `frontend/`: passed.
- Direct live endpoint check: `GET /api/v1/company/AAPL/snapshot` returned HTTP 200 with zero
  warnings in the current configured-provider path.
- Browser smoke at `http://localhost:3000/company/AAPL`: normal overview rendered with peers and
  news; provider-note UI stayed hidden because no live warnings were present.
