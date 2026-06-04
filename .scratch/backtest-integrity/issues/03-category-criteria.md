# BI-3 — Per-category point-in-time eligibility

Status: implemented

## Scope

`screen.eligible(category, params, ticker, D, bars, bench_bars) -> (ok, score, direction)`:

- `long_term`: `as_of` required; FCF>0, `net_debt_to_fcf <= max_debt_to_fcf` (param/6),
  `fcf_margin >= 0.05`; score = FCF yield (fcf / (shares·close@D)); long.
- `income_quality`: dividends_paid>0, `dividend_yield >= min_yield` (param/0.02),
  FCF coverage ≥ `min_fcf_coverage` (param/1.5); score = yield; long.
- `short_term`: `close@D > SMA(slow_days or 100)` and `momentum(120) > 0`; score = momentum; long.
- `risk_rotation`: top-1 by `momentum(lookback_days or 126)` if above SMA(200); else cash; long.
- `short_selling`: `close@D < SMA(100)` and `momentum(120) < 0`; score = −momentum; short.
- `options`: `close@D > SMA(200)`; else cash; long.
- Insufficient price/fundamental data → not eligible.

Note: risk_rotation top-1 selection is applied at the portfolio level in the engine
(rank across candidates), so the eligibility function returns the score and the engine
keeps only the top name.

## Acceptance

- Each category returns a sensible point-in-time decision; fundamental categories return
  not-eligible when `as_of` is None.

## Test

- `backend/tests/test_screen_backtest.py` exercises long_term (fundamental gate) and
  short_term (technical gate) at minimum.
