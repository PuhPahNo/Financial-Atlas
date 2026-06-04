# Phase 04 — In-process refresh tick (no new service)

Status: implemented

## Problem

Values should advance while nobody is watching, without adding a Render cron/service.

## Scope

- `backend/app/main.py`: replace the module-level `init_db()` with a FastAPI `lifespan`
  that calls `init_db()` on startup and, when `settings.live_mark_enabled`, starts a stdlib
  `asyncio` background task; cancels it on shutdown.
- The task loops every `settings.live_mark_interval_seconds` (~60s). Each tick: if
  `market_hours.is_market_open()`, gather active account ids, batch-warm quotes for the
  deduped union of their tickers, then call `ensure_fresh_mark` per account. Wrap the body
  in try/except so one failure never kills the loop; run blocking work via
  `asyncio.to_thread`.
- Safe under the single uvicorn worker (no dup guard needed). Does not start when there is
  no running loop (tests using bare `TestClient(app)` never trigger lifespan).

## Acceptance Criteria

- App boots with the lifespan; `/health` still returns ok.
- With `live_mark_enabled=false`, no task starts; read path still serves values.
- Existing tests remain green and network-free.

## Test

- `PYTHONPATH=backend pytest backend/tests` green (lifespan not triggered by bare client).
- Local smoke: start the API and confirm no errors logged from the tick loop.
