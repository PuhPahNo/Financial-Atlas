# PRD: Active S&P 500 Screening (Engine v2)

Status: implemented

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests` → **88 passed** (+7: active engine + universe).
- Active engine tests (synthetic): enters only after an uptrend (no day-1 buy); take-profit,
  stop-loss, and max-hold each fire with the correct reason; never holds more than top-N;
  all-cash when nothing qualifies. Universe: CSV parse normalizes `BRK.B→BRK-B`; offline
  fetch falls back to the bundled large-cap list.
- Routing verified: a real (non-fixture, non-rule) model routes through `run_active_backtest`
  over `sp500_tickers() ∪ model tickers` and carries the survivorship caveat (no look-ahead
  flag). `npm run build` passed.
- Latency note: scanning ~500 names is cached (prices 6h, companyfacts 7d) and the entry
  scan is gated on free slots; `warm_universe_for_backtests()` pre-warms caches. The first
  cold backtest after deploy is slow, then fast; the engine skips names without data.

## Problem Statement

Models are not actively managed. Each carries a hand-picked `tickers` list (e.g. AAPL/MSFT/
GOOGL), and the engine only ever considers those names. Nothing scans the market. "What
algorithm identified Apple in 2015?" — none did; a person typed it in. The model should
instead watch the **entire S&P 500** and buy any company *when* it meets the model's
criteria, then exit on a stop-loss / take-profit / max-hold / criteria-break.

## Solution

Replace per-model-ticker screening with an **active screener over the S&P 500**:
- Universe = current S&P 500 constituents (free; survivorship over history disclosed).
- Daily event loop: each day, check exits on open positions, then (if slots are free) scan
  the universe for names newly meeting the criteria and enter the best by score.
- **Combination exits**: take-profit %, stop-loss %, max-hold days, or criteria no longer met
  — whichever fires first.
- **Top-N equal weight**: hold at most N names (default 15), equal-weighted; a freed slot is
  refilled by the next-best qualifier.
- Entries/exits at the daily close (free data is end-of-day).

## User Stories

1. As a user, my model scans all ~500 S&P names, not a hand-picked few.
2. As a user, a name is bought on the day it first meets the criteria, point-in-time.
3. As a user, positions exit on take-profit, stop-loss, max-hold, or when criteria break.
4. As a user, the model holds at most N names, equal-weighted, refilling freed slots.
5. As a user, the equity curve reflects this active management, not buy-and-hold of winners.
6. As a user, fundamental models screen the index on as-of-date fundamentals (no look-ahead).
7. As a user, backtests stay usable; the universe is pre-warmed so it isn't 500 cold fetches.
8. As a developer, the scan/exit/sizing logic is unit-testable with synthetic data.

## Implementation Decisions

- **`backtesting/universe.py`** — `sp500_tickers()`: cached (~30d) fetch of S&P 500
  constituents from a free CSV source, with a bundled large-cap fallback used offline / on
  fetch failure. Never raises.
- **`screen.run_active_backtest(...)`** — daily loop over the in-window calendar:
  1. **Exits** — for each open position compute gain vs entry (long: close/entry−1; short:
     entry/close−1) and days held; close on take-profit / stop-loss / max-hold / `eligible`
     false. Realize P&L to cash; apply cost on traded notional.
  2. **Entries** — while held < N, scan universe names not held, evaluate `eligible`
     point-in-time, rank by score, open the best at the daily close; equal-weight target =
     equity/N; apply cost.
  3. Mark net liquidation daily → equity curve (with benchmark).
  Reuses `eligible`, `factors`, `as_of`. Same marking convention as the rule engine (positive
  qty + direction + entry_price; long value qty·price, short qty·(entry−price)). Returns the
  same dict contract (`equity_curve`, `trades`, `metrics`, `warnings`, `holdings`,
  `final_holdings`, `residual_cash`, `served_by`, `date_range`).
  - Exit params from model `parameters` with defaults: `take_profit_pct` 0.25,
    `stop_loss_pct` 0.12, `max_hold_days` 252; `max_positions`/top-N default 15.
- **Routing** — `engine.run_backtest`: real, non-rule strategies → `run_active_backtest`
  with universe = `sp500_tickers()` ∪ model tickers. Fixtures and rule-based models
  unchanged. The monthly `run_screen_backtest` is superseded for catalogue models.
- **Warm/latency** — `warm_universe_for_backtests()` pre-fetches universe price windows
  (and, for fundamental categories, `as_of`/companyfacts) so backtests read warm caches;
  callable from the existing in-process tick / warm path (no new Render service). Names
  without warmed data are simply skipped that day (graceful), and backfilled by the warm job.
- **Caveat** — retain the survivorship/selection note (today's membership applied over
  history). Point-in-time entry is not flagged (it is the expected default).

## Testing Decisions

- Synthetic, deterministic: stub `prices.price_window` and (for fundamentals) `as_of`.
- `run_active_backtest`:
  - enters a name only on/after the day its criteria are met (no day-1 buy);
  - take-profit / stop-loss / max-hold each fire and close the position with the right reason;
  - never holds more than top-N; a freed slot is refilled;
  - all-cash when nothing qualifies.
- `universe.sp500_tickers()` returns the fallback offline and is non-empty.
- Prior art: `backend/tests/test_screen_backtest.py`.

## Out of Scope

- Survivorship-free historical index membership (needs paid data) — disclosed.
- Intraday entries/fills (free data is EOD).
- A persisted precomputed fundamentals DB table — the per-ticker memo + warm job suffice for
  now; a dedicated table can follow if the universe grows well beyond the S&P 500.

## Further Notes

- First backtest of a fundamental model is slow until the universe fundamentals warm
  (companyfacts cached 7d); technical models need only price windows. The warm job removes
  cold-start cost in production.
