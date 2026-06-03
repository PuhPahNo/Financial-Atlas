# Unified Company Snapshot API

Status: implemented

Progress: implemented

## Problem

The company overview page currently fans out into multiple client requests for one ticker. Warm cache
is fast, but the browser still coordinates several calls, error states, and loading states for one
screen.

## Scope

- Add a read-only `/api/v1/company/{ticker}/snapshot` endpoint.
- Compose existing company, valuation, cash-flow-analysis, analyst, news, peers, and price services.
- Preserve existing granular endpoints.
- Add frontend client support and move the overview page to the snapshot path.

## Acceptance Criteria

- Overview page renders from one primary data request.
- Optional sections can fail independently and return warnings instead of blanking the page.
- Endpoint response includes `served_by`, `stale`, and per-section metadata where available.
- Backend tests cover the snapshot shape and partial section failure behavior.

## Implementation Notes

- Added `backend/app/services/snapshot.py`.
- Added `GET /api/v1/company/{ticker}/snapshot`.
- Updated `frontend/lib/api.ts` and the company overview page to load through the snapshot path.
- Existing granular routes remain in place for detail pages.

## QA Evidence

- `backend/.venv/bin/python -m pytest -q` from `backend/`: 22 passed.
- `npm run build` from `frontend/`: passed.
- Browser smoke at `http://localhost:3000/company/AAPL`: overview rendered Apple Inc., peers,
  Wall Street view, and recent news without a loading hang.
- Direct endpoint check: `GET /api/v1/company/AAPL/snapshot` returned HTTP 200 with company,
  valuation, cash-flow-analysis, analyst, news, peers, and prices sections.
