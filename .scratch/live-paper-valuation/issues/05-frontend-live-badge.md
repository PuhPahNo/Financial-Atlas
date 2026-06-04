# Phase 05 — Frontend live value + polling badge

Status: implemented

## Problem

The trader detail page fetches performance once and shows a static value with no freshness
or intraday-change context.

## Scope

- `frontend/lib/paperTradingApi.ts`: add `AccountValue` interface and
  `accountValue(id)` → `GET /paper-trading/accounts/{id}/value`.
- `frontend/components/paper-trading/TraderDetail.tsx`:
  - Keep the existing one-shot `/performance` fetch (curve, attribution, risk).
  - Add a `/value` fetch on mount + `setInterval` poll (~60s) while open; clear on unmount.
  - Render the live `current_value` as the headline figure (fall back to
    `perf.current_value` until the first value arrives), a today's-change pill
    (`day_change` / `day_change_pct`), and a small badge: "as of HH:MM · 15-min delayed"
    when `market_open`, otherwise "Market closed · last close".

## Acceptance Criteria

- `npm run build` in `frontend/` passes.
- Headline shows the live value with a day-change pill and freshness badge.
- Poll stops on unmount (no state updates after close).

## Test

- `npm run build` green; local browser smoke of the badge + polling via preview tools.
