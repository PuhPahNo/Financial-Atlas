# BI-5 — Tests, latency, verify, push

Status: implemented

## Scope

- `backend/tests/test_pit_factors.py` and `backend/tests/test_screen_backtest.py`:
  - factors ignore data after D; `as_of` respects filing dates.
  - screening: no day-1 buy; entry only after criteria flip; all-cash when nothing qualifies;
    fundamental gate withholds a name until its qualifying filing date.
- Full backend suite green; frontend build green.
- Latency sanity: a multi-ticker screening backtest finishes in a few seconds warm.
- Commit + push to main (Render redeploys).

## Acceptance / QA Evidence

- `PYTHONPATH=backend pytest backend/tests` → **81 passed** (63 baseline + 6 live-mark + 6
  new: `test_pit_factors.py`, `test_screen_backtest.py`). `npm run build` → passed.
- Look-ahead proof (synthetic momentum series, decline through 2020-06-30 then uptrend):
  old buy-and-hold would buy on the window's day 1 (2020-01-01); the new engine's first buy
  is **2020-08-01** — only after the uptrend established. All buys dated `> 2020-06-30`.
- All-cash case: strictly declining series → 0 trades, equity flat at starting cash.
- Fundamental gate: with fundamentals "known" only from 2021-01-01, the long_term model has
  no buys before that date (respects filing availability).
- Latency: statements are memoized per ticker for the run (`pit_fundamentals._statements`),
  so companyfacts is parsed once per ticker, not once per rebalance; technical categories
  make no EDGAR calls at all.
