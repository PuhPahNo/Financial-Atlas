# PRD: Live-ish Paper Trader Valuation

Status: implemented

## Problem Statement

When a user opens a simulated trader (a `TraderAccount`) or model, the account value
they see — starting at $100,000 — only changes when they reload the detail page, and
even then it reflects an end-of-day (EOD) daily close that itself changes at most once
per trading day. The number is recomputed on demand by re-running each allocated
strategy's backtest over a rolling 3-year window ending today; positions are never
held statefully and are never marked to a fresher price. From the user's perspective
the balance feels frozen: reloading mid-session shows the same figure, and there is no
sense that the portfolio is "alive" while the market is open.

## Solution

Give every active trader account a **live-ish current value** that refreshes about once
per minute while the US market is open, using only free data (Yahoo quotes, which are
~15-minute delayed). The historical equity curve, attribution, and risk dashboard keep
working exactly as they do today. Layered on top, a lightweight valuation marks the
account's **settled holdings** (the shares the strategies hold going into the next
session) to the latest available quote, and reports the day's change and an explicit
"as of HH:MM · 15-min delayed" / "Market closed" timestamp.

The refresh is driven two ways through one shared, freshness-gated function
(`ensure_fresh_mark`): (a) an in-process tick inside the existing single web service
that pre-warms marks during market hours even when nobody is watching, and (b) the
read path, so any page view brings the mark current on its own. Correctness never
depends on the tick running, so a sleeping/free Render instance self-heals on the next
request.

Hard constraints honored: **free APIs only** (Yahoo + EDGAR; no paid real-time feed),
**no new Render services** (in-process scheduling inside the existing single web
service only), **single uvicorn worker**, and **no new heavyweight dependencies**
(no APScheduler, no tzdata/pytz — Eastern time computed from explicit US DST rules; the
scheduler is a stdlib `asyncio` task started in FastAPI's lifespan).

## User Stories

1. As a paper trader, I want my account's current value to update roughly every minute while the market is open, so that the balance feels live instead of frozen.
2. As a paper trader, I want the value to stop moving when the market is closed and clearly say so, so that I do not mistake a stale number for a broken feature.
3. As a paper trader, I want to see the dollar and percent change for today, so that I can gauge how my simulated portfolio is doing intraday.
4. As a paper trader, I want an explicit "as of HH:MM · 15-min delayed" timestamp on the live value, so that I understand the freshness and limitations of the data.
5. As a paper trader, I want the historical equity curve, attribution, and risk dashboard to keep working unchanged, so that the live feature does not regress anything I rely on.
6. As a paper trader opening a trader detail page, I want the live value to appear quickly without re-running a full 3-year backtest on every refresh, so that the page stays responsive.
7. As a paper trader who leaves the page open, I want it to keep polling and updating the value on its own, so that I do not have to reload manually.
8. As a paper trader, I want the value to be correct for both long buy-and-hold sleeves and short rule-based sleeves, so that the live number reflects what each strategy actually holds.
9. As a paper trader, I want the account's uninvested cash plus the marked value of held positions to add up to the displayed value, so that the live number is internally consistent.
10. As the product owner, I want the live valuation to use only free Yahoo quotes, so that running costs stay at zero.
11. As the product owner, I want no new Render services or cron jobs, so that the deployment footprint and bill do not grow.
12. As the product owner, I want the in-process tick to be safe under a single uvicorn worker, so that there is no duplicate-job racing.
13. As the product owner, I want the tick to be a no-op (and skip network calls) when the market is closed, so that we do not hammer Yahoo overnight or on weekends.
14. As the product owner, I want quotes batched and deduplicated across all active accounts per tick, so that each symbol is fetched at most once per refresh window and we stay polite to Yahoo.
15. As the product owner, I want a short-TTL quote cache so repeated reads within a refresh window coalesce, so that we minimize upstream requests.
16. As a developer, I want the live mark exposed at a dedicated lightweight endpoint separate from the heavy performance endpoint, so that polling is cheap.
17. As a developer, I want one freshness-gated function used by both the tick and the read path, so that there is no duplicated valuation logic.
18. As a developer, I want the settled-holdings snapshot cached with a daily-ish lifetime keyed on the account's allocation signature, so that the expensive backtest only re-runs about once per trading day or when allocations change.
19. As a developer, I want the holdings snapshot to self-heal on read after a sleep gap, so that a paused tick does not leave the value stale.
20. As a developer, I want a market-hours helper that needs no timezone data package, so that it works in the slim production container.
21. As a developer, I want the new endpoint to degrade gracefully (fall back to the EOD baseline, flag staleness) when a quote fetch fails, so that the page never breaks because Yahoo hiccupped.
22. As a developer, I want the backtest engine to additively expose settled holdings (with quantities) without changing the existing equity curve or metrics, so that nothing downstream regresses.
23. As a developer, I want backend tests for the new value endpoint, holdings snapshot, and market-hours gate using the existing TestClient seam, so that behavior is covered.
24. As a paper trader with an account holding multiple sleeves of the same ticker, I want those positions aggregated, so that the live value counts each share once.
25. As a paper trader, I want the live value to never throw away the existing "vs S&P 500 / total return since start" framing, so that the live number complements rather than replaces the historical story.

## Implementation Decisions

- **Backtest engine (additive):** `run_backtest` returns a new `final_holdings` structure
  describing the **settled position going into the next session** — for each held
  instrument: `ticker`, `quantity`, `direction` (`long`/`short`), `entry_price`, and the
  window's `last_close` — plus `residual_cash` (cash held alongside the position). This is
  captured **before** the engine's synthetic end-of-window liquidation, so it represents
  what the strategy actually holds, not the post-sale cash. The existing `holdings`
  (weights), `equity_curve`, `metrics`, and `trades` are unchanged.

- **Settled holdings snapshot (`account_holdings`):** a new function in the accounts
  service runs each allocated sleeve's backtest once and aggregates `final_holdings`
  across sleeves into the account's positions: net long quantities per ticker, short
  positions (with `entry_price`), and total baseline `cash` (account uninvested cash plus
  each sleeve's `residual_cash`). It also records `eod_value` (the baseline value at the
  last close) and the `as_of_date`. Result is cached (filesystem cache) with a daily-ish
  TTL keyed by `(account_id, allocation-signature, last_trading_day)` so the heavy
  backtest re-runs at most ~once per trading day or whenever allocations change.

- **Live quote layer:** Yahoo's `get_quote` is given its **own short-TTL cache** (~60s)
  rather than piggybacking on the 1-hour daily-bar cache, so quotes can be ~1 minute
  fresh while daily bars stay 1-hour cached for backtests. A batched helper fetches quotes
  for the **deduplicated union** of tickers across all active accounts, so each symbol is
  fetched at most once per refresh window. The quote chain stays `FMP → Yahoo`; with no
  FMP key (free constraint) it resolves to Yahoo.

- **Freshness-gated mark (`ensure_fresh_mark`):** the single idempotent operation. It
  loads (or refreshes) the account's settled-holdings snapshot, and — only if the market
  is open and the mark is older than the TTL — fetches live quotes and recomputes:
  - `previous_close_value = cash + Σ_long qty·prev_close + Σ_short qty·(entry_price − prev_close)`
  - `live_value          = cash + Σ_long qty·price      + Σ_short qty·(entry_price − price)`
  - `day_change = live_value − previous_close_value`, `day_change_pct = day_change / previous_close_value`
  When the market is closed it returns the EOD baseline with `market_open=false`. On a
  quote failure it falls back to the EOD baseline and flags `stale=true`. Both the tick
  and the read path call this function; the quote cache + holdings cache provide
  persistence (no new DB table required).

- **Lightweight value endpoint:** `GET /api/v1/paper-trading/accounts/{id}/value` returns a
  compact payload — `current_value`, `eod_value`, `day_change`, `day_change_pct`, `as_of`
  (ISO timestamp), `market_open`, `delayed_minutes` (15), `served_by`, `stale` — wrapped in
  the standard envelope. The existing `/performance` endpoint is untouched.

- **Market-hours helper:** a new `core/market_hours.py` with `is_market_open(now_utc=None)`
  and `last_trading_day(now_utc=None)`. US regular session Mon–Fri 09:30–16:00 ET, minus a
  hardcoded US market holiday set (2024–2027). Eastern offset is computed from explicit US
  DST rules (UTC−4 second Sunday of March → first Sunday of November, else UTC−5) so no
  `tzdata`/`zoneinfo`/`pytz` dependency is needed in the slim container.

- **In-process tick (no new service):** FastAPI gains a `lifespan` handler (replacing the
  module-level `init_db()` call) that, when enabled, starts a stdlib `asyncio` task. The
  task loops on a ~60s interval; on each tick, if the market is open, it batch-warms quotes
  and calls `ensure_fresh_mark` for all active accounts. Gated by a settings flag
  (`live_mark_enabled`, default true) and safe under the project's single uvicorn worker.
  It does not run when the app isn't started with a running event loop (e.g. the test
  TestClient used without a context manager), keeping tests fast and network-free.

- **Frontend:** `paperTradingApi` gets `accountValue(id)`. `TraderDetail` fetches the heavy
  `/performance` once (as today) and additionally polls `/value` on a ~60s interval while
  open, rendering the live `current_value`, today's change pill, and an "as of HH:MM ·
  15-min delayed" / "Market closed" badge. Polling stops on unmount.

- **Settings:** add `live_mark_enabled: bool = True`, `live_mark_interval_seconds: int = 60`,
  and `live_quote_ttl_seconds: int = 60` to `Settings`.

## Testing Decisions

- **What makes a good test here:** assert externally observable behavior through the
  highest available seam — the HTTP API via `TestClient` — and through the pure helper
  functions. Do not assert on cache file layout or internal call counts. Use deterministic
  inputs by monkeypatching the quote function and the holdings snapshot, mirroring the
  existing `test_account_performance_attribution_reconciles`, which monkeypatches
  `account_service.execute_backtest`.

- **Modules tested:**
  - `core/market_hours.py` — unit tests: a known open weekday minute is open; a weekend, a
    pre-open and post-close minute, and a hardcoded holiday are closed; `last_trading_day`
    skips weekends/holidays. Inputs are explicit UTC datetimes (no reliance on "now").
  - `accounts.ensure_fresh_mark` / `/accounts/{id}/value` — with monkeypatched holdings and
    quotes: long-only account marks to `qty·price` and reconciles `cash + positions ==
    current_value`; a short sleeve marks via `entry_price − price`; market-closed returns
    the EOD baseline with `market_open=false`; a raising quote function yields the baseline
    with `stale=true`.
  - Backtest `final_holdings` — a fixture buy-and-hold run reports one long position with a
    positive quantity and the window's last close; the existing equity-curve/metrics
    assertions still pass (regression).

- **Prior art:** `backend/tests/test_paper_trading_api.py` (TestClient + `authenticate`
  helper, monkeypatch of `execute_backtest`, envelope assertions) and
  `backend/tests/test_cache.py`.

- **Pipeline check:** `PYTHONPATH=backend pytest backend/tests` green; `npm run build` in
  `frontend/` green; a local smoke of the `/value` endpoint and the polling badge.

## Out of Scope

- True real-time (sub-15-minute) quotes or streaming (WebSocket/SSE) — requires a paid
  feed, which violates the free-API constraint.
- Intraday re-trading: positions stay fixed during the session; only the mark updates.
  Daily settlement that advances positions from strategy signals remains the backtest's
  job; the snapshot simply reads its settled holdings.
- A persisted per-account snapshot table or migration — the filesystem cache supplies
  persistence for this iteration.
- Per-position intraday history / sparklines for the live value.
- Standalone `PaperPortfolio` (single-strategy) live marks — this PRD covers
  `TraderAccount` profiles; portfolios can adopt the same `ensure_fresh_mark` later.

## Further Notes

- The honest ceiling is Yahoo's ~15-minute delay, so polling faster than ~60s yields no
  fresher data and risks rate-limiting; 60s is the deliberate cadence.
- Because the live overlay marks settled holdings to the previous close and the live
  price, it is independent of the backtest's end-of-window liquidation artifact and of
  whether an in-progress daily bar exists.
- If `live_mark_enabled` is turned off, the read path still serves a correct (EOD or
  lazily re-marked on request) value; only the background pre-warm stops.
