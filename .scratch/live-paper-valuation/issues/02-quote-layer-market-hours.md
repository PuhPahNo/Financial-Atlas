# Phase 02 — Short-TTL quote layer + market-hours gate

Status: implemented

## Problem

Quotes currently piggyback on the 1-hour daily-bar cache, so they cannot be ~1 minute
fresh. There is also no way to know whether the US market is open without a tz package.

## Scope

- `backend/app/providers/yahoo.py`: give `get_quote` its own short-TTL cache (default 60s,
  from `settings.live_quote_ttl_seconds`) via a dedicated chart fetch, leaving the 1-hour
  daily-bar cache for backtests intact.
- `backend/app/services/prices.py`: add `live_quotes(tickers)` that fetches the deduped
  union of tickers (each at most once), returning `{ticker: Quote|None}`; failures per
  ticker are tolerated (None) so one bad symbol does not sink the batch.
- New `backend/app/core/market_hours.py`:
  - `is_market_open(now_utc=None) -> bool` — Mon–Fri 09:30–16:00 ET minus hardcoded US
    holidays (2024–2027).
  - `last_trading_day(now_utc=None) -> date`.
  - Eastern offset from explicit US DST rules (no `tzdata`/`zoneinfo`/`pytz`).
- `backend/app/core/config.py`: add `live_mark_enabled`, `live_mark_interval_seconds`,
  `live_quote_ttl_seconds`.

## Acceptance Criteria

- `is_market_open` true for a known open weekday minute; false for weekend, pre-open,
  post-close, and a hardcoded holiday.
- `last_trading_day` skips weekends/holidays.
- `live_quotes(["AAA","AAA","BBB"])` fetches each symbol once.

## Test

- New `backend/tests/test_market_hours.py` with explicit UTC datetimes.
