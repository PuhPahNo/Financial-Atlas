# Cache Metadata And Single-Flight

Status: implemented

Progress: implemented

## Problem

The cache layer exists, but UX trust depends on seeing freshness and preventing duplicated provider
work during cold ticker loads.

## Scope

- Surface `stale`, `served_by`, `as_of`, and `warnings` consistently.
- Add or verify single-flight behavior for concurrent cold requests.
- Add timing instrumentation for hot financial endpoints.

## Acceptance Criteria

- Repeated warm requests stay under the PRD target.
- Concurrent cold requests result in one upstream provider fetch per cache key.
- UI can label stale or partial data without custom per-page logic.

## Implementation Notes

- Added scoped cache tracing in `backend/app/core/cache.py`.
- Cache results now carry `stored_at` and `status` (`miss`, `hit`, `stale`, or `bypass`).
- Snapshot sections now include cache summaries: status, hit/miss/stale counts, `as_of`,
  `max_age_seconds`, and stale state.
- The company snapshot route now promotes overall `stale`, `as_of`, and warning metadata into the
  top-level API envelope.
- The frontend API envelope type now allows optional `as_of` and `warnings`.

## QA Evidence

- `backend/.venv/bin/python -m pytest tests/test_cache.py tests/test_company_snapshot_api.py -q`
  from `backend/`: 6 passed.
- `backend/.venv/bin/python -m pytest -q` from `backend/`: 26 passed.
- `npm run build` from `frontend/`: passed.
- Direct live endpoint check: `GET /api/v1/company/AAPL/snapshot` returned HTTP 200 with
  `meta.as_of`, `meta.stale=false`, section cache metadata, and no warnings.
- Browser smoke at `http://localhost:3000/company/AAPL`: overview rendered Apple Inc., valuation,
  peers, Wall Street view, and news without an error page.
