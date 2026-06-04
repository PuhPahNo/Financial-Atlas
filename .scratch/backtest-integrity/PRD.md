# PRD: Backtest Integrity — No Look-Ahead, Point-in-Time Entry

Status: implemented

## Problem Statement

Paper-trading models produce wildly optimistic, illegitimate backtests. 19 of 21 seed
models have no `parameters.rules`, so the engine runs plain buy-and-hold: it buys the
**first listed ticker on day 1** of the window and holds to the end, evaluating **none**
of the model's stated criteria. Combined with a hand-picked ticker universe chosen with
hindsight (NVDA, AAPL, …), every such backtest "buys" a known future winner at the start
of the window. The result is double bias:

- **Look-ahead:** the entry happens on day 1 regardless of whether the model's criteria
  were met then; the criteria are never actually computed.
- **Selection / survivorship:** the candidate list was curated today knowing who won.

So a 2009–2014 backtest of a momentum or FCF model "buys" NVDA/AAPL on day one and shows
market-crushing returns the model never could have generated. The advertised
methodology is decorative.

## Solution

Replace the cheating buy-and-hold path with a **point-in-time screening engine**: at each
rebalance date D, evaluate the model's criteria for each candidate using **only data
available at D** (prices up to D; fundamentals as-reported and *filed* on or before D),
hold only the names that pass, rebalance periodically, and mark to market daily. A
position is opened at D only because the criteria actually triggered at D — never because
the ticker is a known winner.

- **Technical criteria** (momentum, trend, relative strength, breakout, volatility) are
  computed point-in-time from the price bars already fetched.
- **Fundamental criteria** (FCF margin, leverage, dividend coverage, shareholder yield)
  are computed from EDGAR `companyfacts`, which carries a `filed` date on every value —
  one cached fetch per ticker, then in-memory "what was known as of D" filtering. Free,
  and no per-rebalance network calls, so latency/UX stay intact.
- Rule-based models (those with `parameters.rules`) already evaluate signals
  point-in-time and are unchanged. Fixture backtests (`use_fixture_data=True`) keep the
  deterministic buy-and-hold path for contract tests.

Selection/survivorship from the user-specified universe cannot be fully removed with free
data (no survivorship-free historical constituents), so it is **disclosed** via an
explicit caveat rather than faked.

## User Stories

1. As a user, I want a backtest to only buy a stock at a historical date if the model's criteria were actually met then, so the results reflect the model and not hindsight.
2. As a user, I want a 2009–2014 backtest to NOT buy NVDA/AAPL unless they passed the criteria as of that period, so I can trust the numbers.
3. As a user, I want fundamental criteria evaluated using only filings available at the simulated date, so there is no restatement or future-data leakage.
4. As a user, I want technical criteria (momentum, trend, breakout) evaluated from prices up to the simulated date only, so entries are realistic.
5. As a user, I want positions to rebalance over time as eligibility changes, so the model can enter and exit names as criteria flip.
6. As a user, I want the model to sit in cash when nothing qualifies, so it does not force a position.
7. As a user, I want short models to enter shorts only when weakness criteria are met point-in-time, so bearish bets are legitimate too.
8. As a user, I want the headline return, equity curve, and trades to come from this point-in-time simulation, so the displayed performance is honest.
9. As a user, I want a clear caveat that the candidate universe is user-specified and survivorship is not modeled, so I understand the remaining limitation.
10. As a user, I want backtests to stay reasonably fast, so the UX is not degraded by the fundamentals work.
11. As a user, I want the live trader-account value to be built on these honest holdings, so the live mark inherits the corrected positions.
12. As a developer, I want the screening logic isolated and unit-testable, so point-in-time correctness can be asserted.
13. As a developer, I want existing fixture and rule-based tests to keep passing, so the change is non-regressive.
14. As a developer, I want fundamentals fetched once per ticker and cached, so the engine does not make per-date network calls.
15. As a user, I want each category (long-term value/quality, income, momentum/short-term, rotation, short, options proxy) to use a defensible point-in-time rule, so every model is simulated rather than faked.

## Implementation Decisions

- **New module `backtesting/factors.py`** — point-in-time technical factors over a sorted
  bar list, each using only bars with `date <= D`: `momentum(lookback)`, `trend` (close vs
  SMA), `sma`, `relative_strength(vs benchmark)`, `volatility`, `new_high(channel)`,
  `drawdown`, `pct_change(window)`.

- **New module `backtesting/pit_fundamentals.py`** — `as_of(ticker, D)` returns the most
  recent annual fundamentals whose `filing_date <= D` (from `sec_edgar.get_income_statements
  / get_balance_sheets / get_cash_flows`, which already expose `filing_date`), plus derived
  metrics: `fcf`, `fcf_margin`, `fcf_conversion`, `net_debt`, `net_debt_to_fcf`,
  `dividends_paid`, `shareholder_yield`, `shares`. Returns `None` if nothing was filed by D.
  One cached `companyfacts` fetch per ticker; in-memory date filtering. Tolerant of missing
  data (returns None → candidate simply not eligible).

- **New module `backtesting/screen.py`** — `run_screen_backtest(...)`: prefetch daily bars
  per candidate over `[start − warmup, end]`; build the trading calendar; rebalance monthly
  (first trading day of each month, plus the window start). At each rebalance date, call a
  category eligibility function per candidate, select eligible names, rank by score, cap at
  `max_positions` (default 8), equal-weight (shorts negative), apply transaction+slippage
  costs on turnover, and mark daily to build the equity curve. Returns the same dict shape
  as `run_backtest` (`equity_curve`, `trades`, `metrics`, `warnings`, `holdings`,
  `final_holdings`, `residual_cash`, `served_by`, `date_range`).

- **Category eligibility (`screen.py`)** — `eligible(category, params, ticker, D, bars, bench_bars) -> (ok, score, direction)`:
  - `long_term`: fundamentals as-of D required; gate FCF>0, `net_debt_to_fcf <= max_debt_to_fcf` (param/6), `fcf_margin >= 0.05`; score = FCF yield (FCF / (shares·price@D)); long.
  - `income_quality`: dividends_paid>0, `dividend_yield >= min_yield` (param/0.02), FCF covers dividends ≥ `min_fcf_coverage` (param/1.5); score = dividend yield; long.
  - `short_term`: `close@D > SMA(slow_days or 100)` AND `momentum(120d) > 0`; score = momentum; long.
  - `risk_rotation`: rank by `momentum(lookback_days or 126)`; hold the single top name only if above its SMA(200), else cash; long.
  - `short_selling`: `close@D < SMA(100)` AND `momentum(120d) < 0`; score = −momentum; **short** (capped by `max_short_exposure` or 0.25).
  - `options`: hold underlying only when `close@D > SMA(200)` (point-in-time trend filter), else cash; long.
  - All gates also require sufficient price history and (for fundamental gates) `as_of` data; otherwise not eligible.

- **Routing (`engine.run_backtest`)** — if `use_fixture_data` → existing buy-and-hold
  (deterministic contract path, unchanged). Else if `parameters.rules` → existing
  `_run_rules` (unchanged). Else → `run_screen_backtest` (new). The screening result keeps
  the same contract so `service.run_backtest`, `account_performance`, and `account_holdings`
  are unaffected structurally.

- **Caveats / honesty** — every real backtest result appends warnings:
  "Point-in-time entry — positions open only when criteria were met at that date (no
  look-ahead)." and "Candidate universe is user-specified; survivorship/selection bias is
  not modeled." Surface a short methodology note in the model detail UI.

## Testing Decisions

- **What makes a good test:** assert externally observable, point-in-time behavior with
  deterministic inputs — never internal call counts. Use synthetic bar series and stubbed
  `as_of` fundamentals so eligibility is fully determined.
- **Modules tested:**
  - `factors.py` — momentum/trend/SMA/new_high computed only from bars ≤ D (a future spike
    after D does not change the value at D).
  - `pit_fundamentals.as_of` — given periods with filing dates, a date before the later
    filing returns the earlier period; future filings are invisible.
  - `screen.run_screen_backtest` — a momentum model on a series that is in a downtrend early
    and an uptrend later only **enters after** the uptrend begins (no day-1 buy); a name
    whose fundamentals only qualify after a later filing is not held before that filing; a
    window where nothing qualifies stays in cash (equity flat at starting cash).
  - Routing — fixture and rule-based paths unchanged (existing tests stay green).
- **Prior art:** `backend/tests/test_paper_trading_api.py`, `backend/tests/test_strategy_validation.py`.
- **Latency check:** a real screening backtest over a multi-ticker fundamental model
  completes in a few seconds on warm cache; fundamentals fetched once per ticker.

## Out of Scope

- A survivorship-free historical universe (delisted names, historical index constituents)
  — not feasible with free data; disclosed as a caveat.
- Exact replication of every model's prose methodology — criteria are defensible
  point-in-time approximations per category, clearly labeled.
- Intraday fills, options-chain modeling, tax/borrow costs for shorts.
- Backfilling/altering already-stored historical run records.

## Further Notes

- Fundamentals stay free and fast because `companyfacts` is one cached request per ticker
  (7-day disk + in-memory), and as-of filtering is pure in-memory work.
- The live trader-account value (PRD live-paper-valuation) automatically inherits the
  corrected holdings, since `account_holdings` runs these backtests.
