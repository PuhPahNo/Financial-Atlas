# Phase 06 — Tests, QA, pipeline verification

Status: implemented

## Problem

The feature must be verified end to end before shipping to production (Render redeploy on
push to main).

## Scope

- Backend: `test_market_hours.py` (open/closed/holiday/last-trading-day) and new
  `/accounts/{id}/value` tests (long, short, market-closed, quote-failure) plus the
  `final_holdings` regression assertion.
- Run the full backend suite and the frontend build.
- Local pipeline smoke: boot the app, hit `/health` and `/accounts/{id}/value`, confirm the
  detail page renders the live value + badge and polls.

## Acceptance Criteria

- `PYTHONPATH=backend pytest backend/tests` all green.
- `npm run build` in `frontend/` green.
- `/value` returns a well-formed envelope; the badge reflects market open/closed.
- No regressions in existing paper-trading/backtesting tests.

## Test / QA Evidence

- `PYTHONPATH=backend pytest backend/tests` → **75 passed** (was 63; +7 market-hours,
  +5 value/holdings).
- `npm run build` in `frontend/` → **passed** (all routes compiled, paper-trading bundle OK).
- Real uvicorn boot → `Application startup complete` (lifespan + background tick start cleanly).
- `/accounts/{id}/value` exercised through the real ASGI route **under an active lifespan**
  (network-free, holdings/quotes stubbed): returned a 200 envelope with
  `current_value=1600.0` (500 cash + 10×110), `day_change=100.0`, `day_change_pct=0.0667`,
  `market_open=true`, `served_by=yahoo`, `delayed_minutes=15`, `stale=false`.
- Note: a live-Yahoo backtest smoke could not complete in the build sandbox (outbound
  network is restricted); the route logic and envelope are fully covered by the offline
  ASGI tests above and will hit real quotes once deployed.
