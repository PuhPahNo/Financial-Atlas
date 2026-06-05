# PRD: Point-in-Time Index Membership + Expanded Universe

Status: implemented

## QA Evidence

- `PYTHONPATH=backend pytest backend/tests` → **93 passed** (+5: reconstruct, members_on,
  change-log parse, investable_superset/ETFs, engine membership filter).
- `reconstruct` verified backward (post-asof additions excluded, removals restored).
- Engine test: a technically-qualifying name is not bought until its membership date.
- CSV change-log parse handles ISO and quoted named dates; ETFs fold into the superset.
- `npm run build` passed. Degrades to current membership offline (no regression);
  live change-log validates on Render (network).

## Problem Statement

Backtests scan *today's* S&P 500 over history, so they silently study only the ~half of
names that survived and never see the ~half that were removed (acquired, shrank, delisted).
At a 20-year horizon that's a large upward (survivorship) bias. Separately, the investable
universe is too narrow — models should also be able to trade major ETFs / index funds, not
just individual S&P 500 stocks.

## Solution

1. **Point-in-time membership (free).** Reconstruct who was in the S&P 500 on any past date
   by taking the current list and applying the published add/delete change-log *backward*.
   Backtests then scan the index *as it was* on each date — including names later removed —
   removing most of the survivorship bias with pure code (no paid data).
2. **Expanded universe.** Add a curated set of major ETFs / index funds (broad market,
   sectors, bonds, commodities, styles) to the investable universe alongside the full S&P
   500. ETFs have no EDGAR fundamentals, so they're naturally eligible only for technical /
   rotation models and skipped by fundamental ones.

Honest limits: the change-log source is best-effort and free; if it's unavailable the system
degrades to current membership (no regression). Free price history for *delisted* names is
still incomplete (Yahoo drops them), so a residual survivorship gap remains — disclosed.

## User Stories

1. As a user, a 2005-start backtest considers the companies that were in the S&P 500 in 2005, not today's list.
2. As a user, names removed from the index over time are included while they were members.
3. As a user, models can also buy major ETFs / index funds (SPY, QQQ, sector SPDRs, TLT, GLD, …).
4. As a user, fundamental models ignore ETFs (no financials) but technical/rotation models can hold them.
5. As a user, if the membership source is down, backtests still run (fall back to current membership).
6. As a developer, the backward-reconstruction is a pure, unit-tested function.
7. As a developer, the membership lookup is memoized so the daily scan stays fast.
8. As a user, the residual delisted-price gap is disclosed, not hidden.

## Implementation Decisions

- **`universe.py`**
  - `ETF_UNIVERSE` — bundled curated list of ~40–50 major ETFs / index funds.
  - `_changes()` — best-effort fetch of the S&P 500 add/delete change-log
    `[{date, added, removed}]` from a free CSV source, cached ~30 days; returns `[]` on
    failure (→ degrade to current membership).
  - `reconstruct(current, changes, asof)` — pure: start from the current set and reverse
    every change dated after `asof` (newest→oldest: drop the added ticker, restore the
    removed ticker). Returns the membership set as of `asof`.
  - `members_on(asof)` — `reconstruct(sp500_tickers(), _changes(), asof)`, memoized per date.
  - `investable_superset()` — current S&P 500 ∪ every ticker ever added/removed in the
    change-log ∪ `ETF_UNIVERSE` (the set to prefetch prices for).
- **`screen.run_active_backtest`** — new optional `membership_on: Callable[[date], set]`.
  When provided, the daily entry scan only considers candidates with `t in membership_on(d)`
  (point-in-time membership). Held positions are not force-sold on index removal; normal
  exits apply. When `None`, scans the whole passed universe (prior behavior).
- **Routing (`engine.run_backtest`)** — real catalogue models: prefetch
  `investable_superset() ∪ model tickers`; `membership_on(d) = members_on(d) ∪ ETF set ∪
  model tickers`. Gated by `settings.backtest_point_in_time_membership` (default True);
  off → `membership_on=None` (full current universe each day).
- **Resilience/latency** — dead tickers (no free price data) are skipped (already) and their
  failed fetch is tolerated; `warm_universe_for_backtests()` covers the superset. The
  superset is larger (~1k incl. historical removals + ETFs), so prod relies on the warm
  caches; first cold backtest is slow, then fast.

## Testing Decisions

- Pure/deterministic, no network:
  - `reconstruct` — synthetic change-log: a ticker added after `asof` is excluded as-of; a
    ticker removed after `asof` is restored as-of; changes on/before `asof` are kept.
  - `members_on` — with `_changes` stubbed, returns the right historical set.
  - `ETF_UNIVERSE` present in `investable_superset`; fundamental `as_of` returns None for a
    typical ETF (so fundamental models skip it).
  - `run_active_backtest` with a `membership_on` that excludes a ticker before date X — that
    ticker is never bought before X even though it qualifies technically.
- Prior art: `backend/tests/test_universe.py`, `backend/tests/test_active_backtest.py`.

## Out of Scope

- Complete delisted-name price history (Yahoo drops it; needs paid data) — disclosed.
- Other indices' historical membership (Nasdaq-100, Russell) — S&P 500 only for now.
- Forcing sells when a held name leaves the index (kept simple: normal exits apply).

## Further Notes

- With the change-log source live (on Render), this removes most survivorship bias for free.
  Offline/in tests it degrades to current membership, so there is never a regression.
