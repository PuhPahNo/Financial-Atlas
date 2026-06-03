# Screener Universe And Warm Jobs

Status: implemented

Progress: implemented

## Problem

Discovery workflows need a reliable ticker universe and cache warming for watchlisted, recently
viewed, and screened companies.

## Scope

- Define the initial local universe source and ingestion UX.
- Warm company overview, cash-flow-analysis, valuation, and price history for tracked tickers.
- Add job logs with skipped/failed counts.

## Acceptance Criteria

- Screener can run on a populated universe without manual one-off ticker calls.
- Warm jobs are idempotent and safe to rerun.
- Failed tickers do not abort the full job.

## Implementation Notes

- Added a backend-owned starter universe in `backend/app/services/screener.py`.
- Added `POST /api/v1/screener/seed` to ingest the starter universe or an explicit list.
- Added `POST /api/v1/screener/warm` to warm explicit tickers or, when no tickers are supplied,
  the tracked local dataset.
- `tracked_tickers` now combines existing screener snapshots, watchlist items, optional defaults,
  and optional extra tickers with deduping.
- `warm_ticker` warms snapshot, company overview, cash-flow-analysis, valuation, and price history
  and returns per-domain status.
- `backend/app/jobs/refresh.py` now uses tracked tickers and returns detailed refreshed/failed/skipped
  logs.
- Screener UI now has `Seed starter universe` and `Warm dataset` actions plus a compact job summary.
- Explicit warm requests now warm only the explicit tickers; the refresh job remains responsible for
  tracked/watchlist warming.

## QA Evidence

- `backend/.venv/bin/python -m pytest tests/test_screener_warm.py -q` from `backend/`: 4 passed.
- `backend/.venv/bin/python -m pytest -q` from `backend/`: 36 passed.
- `npm run build` from `frontend/`: passed.
- Browser smoke at `http://localhost:3000/screener`: seed and warm controls rendered with no error
  page.
- Direct live endpoint check: `POST /api/v1/screener/warm` with `FAKEINVALID123` returned HTTP 200,
  `tickers=1`, `warmed=0`, `failed=1`, and per-domain failure details.
- Direct live endpoint check: `GET /api/v1/screener/universe` returned local universe count,
  starter-universe count, and watchlist tickers.
- Live warm verification populated real tracked/watchlist snapshots; these are useful screener data,
  not disposable test-only rows.
